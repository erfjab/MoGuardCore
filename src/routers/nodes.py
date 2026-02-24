from fastapi import APIRouter, HTTPException
from src.dependencies import GetAsyncSession, GetNode, GetCurrentOwner
from src.db import Node
from src.models.nodes import NodeResponse, NodeCreate, NodeUpdate, NodeStatsResponse
from src.guard_node import GuardNodeManager

router = APIRouter(prefix="/nodes", tags=["Nodes"])


@router.get("", response_model=list[NodeResponse])
async def get_nodes(current: GetCurrentOwner, db: GetAsyncSession) -> list[NodeResponse]:
    """Get a list of all nodes."""
    return await Node.get_all(db)


@router.get("/stats", response_model=NodeStatsResponse)
async def get_node_stats(current: GetCurrentOwner, db: GetAsyncSession) -> NodeStatsResponse:
    """Get statistics about nodes."""
    return await Node.get_stats(db)


@router.post("", response_model=NodeResponse)
async def create_node(
    current: GetCurrentOwner,
    data: NodeCreate,
    db: GetAsyncSession,
) -> NodeResponse:
    """Create a new node."""
    validate = await GuardNodeManager.register(
        username=data.username, password=data.password, host=data.host, category=data.category
    )
    if not validate:
        raise HTTPException(
            status_code=400, detail="Failed to register node with the guard node manager. Please check the provided details."
        )
    return await Node.create(
        db,
        data=data,
        access=validate,
    )


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(current: GetCurrentOwner, node: GetNode) -> NodeResponse:
    """Get a single node by ID."""
    return node


@router.put("/{node_id}", response_model=NodeResponse)
async def update_node(
    current: GetCurrentOwner,
    node: GetNode,
    data: NodeUpdate,
    db: GetAsyncSession,
) -> NodeResponse:
    """Update an existing node."""
    validate = None
    if data.username or data.password or data.host:
        validate = await GuardNodeManager.register(
            username=data.username or node.username,
            password=data.password or node.password,
            host=data.host or node.host,
            category=node.category,
        )
        if not validate:
            raise HTTPException(
                status_code=400,
                detail="Failed to register node with the guard node manager. Please check the provided details.",
            )
    return await Node.update(db, node, data=data, access=validate)


@router.post("/{node_id}/enable", response_model=NodeResponse)
async def enable_node(current: GetCurrentOwner, node: GetNode, db: GetAsyncSession) -> NodeResponse:
    """Enable a node by ID."""
    return await Node.enable(db, node)


@router.post("/{node_id}/disable", response_model=NodeResponse)
async def disable_node(current: GetCurrentOwner, node: GetNode, db: GetAsyncSession) -> NodeResponse:
    """Disable a node by ID."""
    return await Node.disable(db, node)


@router.delete("/{node_id}", response_model=dict)
async def delete_node(current: GetCurrentOwner, node: GetNode, db: GetAsyncSession) -> dict:
    """Delete a node by ID."""
    await Node.remove(db, node)
    return {"message": "Node deleted successfully"}
