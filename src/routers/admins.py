from typing import Optional, Annotated
import json
import pyotp
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request, Response, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from src.db import Admin, Subscription
from src.utils.auth import Auth
from src.utils.cache import AdminCache
from src.dependencies import GetAsyncSession, GetAdmin, GetCurrentOwner, GetCurrentAdmin, BlockOwnerAction
from src.models.subscriptions import SubscriptionResponse
from src.utils.notif import NotificationService
from src.models.admins import (
    AdminCurrentUpdate,
    AdminResponse,
    AdminCreate,
    AdminUpdate,
    AdminToken,
    AdminUsageLogsResponse,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admins/token")

router = APIRouter(prefix="/admins", tags=["Admins"])


@router.get("", response_model=list[AdminResponse])
async def get_admins(current: GetCurrentOwner, db: GetAsyncSession) -> list[AdminResponse]:
    """Get a list of all admins."""
    return await Admin.get_all(db)


@router.post("", response_model=AdminResponse)
async def create_admin(
    current: GetCurrentOwner,
    data: AdminCreate,
    db: GetAsyncSession,
) -> AdminResponse:
    """Create a new admin."""
    check_exists = await Admin.check_exists(db, data.username)
    if check_exists:
        raise HTTPException(status_code=400, detail="Admin with this username already exists")
    admin = await Admin.create(
        db,
        data=data,
    )
    AdminCache.update(admin)
    return admin


@router.post("/token", response_model=AdminToken)
async def create_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: GetAsyncSession,
    request: Request,
    totp_code: Optional[str] = None,
) -> Optional[AdminToken]:
    admin = await Admin.verify_credentials(db, form_data.username, form_data.password)
    if not admin:
        await NotificationService.admin_failed_login(
            form_data.username, form_data.password, totp_code, request.client.host, request.headers.get("User-Agent", "")
        )
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if admin.totp_status:
        if not totp_code:
            await NotificationService.admin_failed_login(
                form_data.username,
                form_data.password,
                totp_code,
                request.client.host,
                request.headers.get("User-Agent", ""),
            )
            raise HTTPException(status_code=401, detail="TOTP code required")
        totp = pyotp.TOTP(admin.totp_secret)
        if not totp.verify(totp_code):
            await NotificationService.admin_failed_login(
                form_data.username,
                form_data.password,
                totp_code,
                request.client.host,
                request.headers.get("User-Agent", ""),
            )
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

    await NotificationService.admin_login(admin, request.client.host, request.headers.get("User-Agent", ""))
    await Admin.update_last_login(db, admin)
    return AdminToken(access_token=Auth.create(admin), token_type="bearer")


@router.get("/current", response_model=AdminResponse)
async def get_current_admin(current: GetCurrentAdmin) -> AdminResponse:
    """Get the current authenticated admin."""
    return current


@router.get("/current/usages", response_model=AdminUsageLogsResponse)
async def get_current_admin_usages(current: GetCurrentAdmin, db: GetAsyncSession) -> AdminUsageLogsResponse:
    """Get usage logs for the current admin."""
    raise HTTPException(status_code=404, detail="Not implemented")


@router.put("/current", response_model=AdminResponse)
async def update_current_admin(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
    data: AdminCurrentUpdate = Body(...),
    code: Optional[str] = Body(default=None, description="Current 6-digit TOTP code"),
) -> AdminResponse:
    """Update the current admin."""
    if data.totp_status is not None and data.totp_status != current.totp_status:
        if data.totp_status and not current.totp_secret:
            raise HTTPException(status_code=400, detail="Generate a TOTP secret first by revoking sessions.")
        if not pyotp.TOTP(current.totp_secret).verify(code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code")

    updated = await Admin.update_current(db, current, data=data)
    AdminCache.update(updated)
    return updated


@router.post("/current/revoke", response_model=AdminResponse)
async def revoke_current_admin_api_key(current: GetCurrentAdmin, db: GetAsyncSession) -> AdminResponse:
    """Revoke API key for the current admin."""
    updated = await Admin.revoke_api_key(db, current)
    AdminCache.update(updated)
    return updated


@router.post("/current/totp/revoke")
async def revoke_totp_secret(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
    code: Optional[str] = Body(default=None, embed=True, description="Current 6-digit TOTP code"),
):
    """Rotate the current admin TOTP secret and return provisioning info for verification."""
    requires_totp = bool(current.totp_secret and current.totp_status)
    if requires_totp:
        if not code:
            raise HTTPException(status_code=401, detail="TOTP code required to revoke")
        totp = pyotp.TOTP(current.totp_secret)
        if not totp.verify(code, valid_window=1):
            raise HTTPException(status_code=401, detail="Invalid TOTP code")
    await Admin.rotate_totp_secret(db, current)
    uri = pyotp.TOTP(current.totp_secret_pending).provisioning_uri(name=current.username, issuer_name="GuardCore")
    return {
        "secret": current.totp_secret_pending,
        "uri": uri,
        "message": "Secret generated. Scan QR code and verify with /totp/verify endpoint.",
    }


@router.post("/current/totp/verify")
async def verify_totp_secret(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
    code: str = Body(..., embed=True, description="6-digit TOTP code from authenticator app"),
):
    """Verify pending TOTP secret and activate it."""
    if not current.totp_secret_pending:
        raise HTTPException(status_code=400, detail="No pending TOTP secret. Call /totp/revoke first.")
    if not pyotp.TOTP(current.totp_secret_pending).verify(code):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    await Admin.activate_totp_pending(db, current)
    return {"message": "TOTP verified and activated successfully"}


@router.get("/current/backup", response_class=Response)
async def get_current_admin_backup(
    current: GetCurrentAdmin,
    db: GetAsyncSession,
) -> Response:
    """Get a backup of the current admin and their subscriptions."""
    if current.last_backup_at and (datetime.utcnow() - current.last_backup_at) < timedelta(minutes=10):
        raise HTTPException(status_code=429, detail="Backup rate limit exceeded. Please try again later.")
    await Admin.update_last_backup(db, current)
    subs = await Subscription.get_all(db=db, owner_id=current.id)
    return Response(
        content=json.dumps(
            {
                "admin": AdminResponse.model_validate(current).model_dump(mode="json"),
                "subscriptions": [SubscriptionResponse.model_validate(sub).model_dump(mode="json") for sub in subs],
                "exported_at": datetime.utcnow().isoformat(),
            },
            indent=2,
            default=str,
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=backup_{current.username}_{datetime.utcnow().strftime('%Y%m%d%H%M')}.json"
        },
    )


@router.get("/{username}", response_model=AdminResponse)
async def get_admin(current: GetCurrentOwner, admin: GetAdmin) -> AdminResponse:
    """Get a single admin by Username."""
    return admin


@router.get("/{username}/usages", response_model=AdminUsageLogsResponse)
async def get_admin_usages(current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession) -> AdminUsageLogsResponse:
    """Get usage logs for an admin by Username."""
    raise HTTPException(status_code=404, detail="Not implemented")


@router.put("/{username}", response_model=AdminResponse)
async def update_admin(
    current: GetCurrentOwner,
    admin: GetAdmin,
    data: AdminUpdate,
    db: GetAsyncSession,
) -> AdminResponse:
    """Update an existing admin."""
    if data.totp_status is not None and data.totp_status != admin.totp_status:
        if data.totp_status and not admin.totp_secret:
            raise HTTPException(status_code=400, detail="Generate a TOTP secret first by revoking sessions.")

    updated = await Admin.update(db, admin, data=data)
    AdminCache.update(updated)
    return updated


@router.post("/{username}/enable", response_model=AdminResponse)
async def enable_admin(current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction) -> AdminResponse:
    """Enable an admin by Username."""
    updated = await Admin.enable(db, admin)
    AdminCache.update(updated)
    return updated


@router.post("/{username}/disable", response_model=AdminResponse)
async def disable_admin(current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction) -> AdminResponse:
    """Disable an admin by Username."""
    updated = await Admin.disable(db, admin)
    AdminCache.update(updated)
    return updated


@router.post("/{username}/revoke", response_model=AdminResponse)
async def revoke_admin_api_key(
    current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction
) -> AdminResponse:
    """Revoke API key for an admin by Username."""
    updated = await Admin.revoke_api_key(db, admin)
    AdminCache.update(updated)
    return updated


@router.delete("/{username}", response_model=dict)
async def delete_admin(current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction) -> dict:
    """Delete an admin by Username."""
    if admin.current_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete an admin with active subscriptions")
    await Admin.remove(db, admin)
    AdminCache.remove(admin)
    return {"message": "Admin deleted successfully"}


@router.get("/{username}/subscriptions", response_model=list[SubscriptionResponse])
async def get_admin_subscriptions(
    current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction
) -> list[SubscriptionResponse]:
    """Get subscriptions of an admin by Username."""
    return admin.subscriptions


@router.post("/{username}/subscriptions/activate", response_model=dict)
async def activate_admin_subscriptions(
    current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction
) -> dict:
    """Activate subscriptions of an admin by Username."""
    await Subscription.bulk_activate(db, admin=admin)
    return {"message": "Subscriptions activated successfully"}


@router.post("/{username}/subscriptions/deactivate", response_model=dict)
async def deactivate_admin_subscriptions(
    current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction
) -> dict:
    """Deactivate subscriptions of an admin by Username."""
    await Subscription.bulk_deactivate(db, admin=admin)
    return {"message": "Subscriptions deactivated successfully"}


@router.delete("/{username}/subscriptions", response_model=dict)
async def delete_admin_subscriptions(
    current: GetCurrentOwner, admin: GetAdmin, db: GetAsyncSession, _: BlockOwnerAction
) -> dict:
    """Delete subscriptions of an admin by Username."""
    await Subscription.bulk_remove_by_admin(db, admin)
    await Admin.sync_current_counts(db)
    return {"message": "Subscriptions deleted successfully"}
