#!/bin/bash

### Basic setup
USERNAME="erfjab"
SCRIPT_NAME="moguardcore"
DEFAULT_BRANCH="master"
INSTALL_BASE_DIR="/opt/erfjab/${SCRIPT_NAME}"
REPO_URL="https://github.com/${USERNAME}/${SCRIPT_NAME}.git"
GITHUB_TOKEN="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"
REPO_URL_WITH_TOKEN="https://${GITHUB_TOKEN}:x-oauth-basic@github.com/${USERNAME}/${SCRIPT_NAME}.git"

### Logging functions
log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

### Subscription installation functions

check_instance_name() {
    local instance_name="$1"
    if [[ -z "$instance_name" ]]; then
        error "Instance name is required"
    fi
    if [[ ! -d "$INSTALL_BASE_DIR/$instance_name" ]]; then
        error "Instance '$instance_name' does not exist"
    fi
}

check_branch_name() {
    local branch_name="$1"
    log "Checking branch name '$branch_name'"
    if [[ -z "$branch_name" ]]; then
        error "Branch name is required"
    fi
    # check if branch exists in remote repo
    if ! git ls-remote --heads "$REPO_URL_WITH_TOKEN" "$branch_name" | grep -q "$branch_name"; then
        error "Branch '$branch_name' does not exist in the repository"
    fi
    success "Branch name '$branch_name' is valid"
}

check_not_exists() {
    local instance_name="$1"
    if [[ -z "$instance_name" ]]; then
        error "Instance name is required"
    fi
    if [[ -d "$INSTALL_BASE_DIR/$instance_name" ]]; then
        error "Instance '$instance_name' already exists"
    fi
}

subscription_show_env() {
    # open instance env file in nano editor
    local instance_name="$1"
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    local env_file="$instance_dir/.env"
    if [[ ! -f "$env_file" ]]; then
        error "Environment file '$env_file' does not exist"
    fi
    nano "$env_file"
}

subscription_create_env() {
    # create env file with default values
    local instance_name="$1"
    local instance_pass="$2"
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    local env_file="$instance_dir/.env"
    if [[ -f "$env_file" ]]; then
        error "Environment file '$env_file' already exists. It will be replaced."
    fi
    if [[ ! -f "$instance_dir/.env.example" ]]; then
        error "Example environment file '$instance_dir/.env.example' does not exist"
    fi
    cp "$instance_dir/.env.example" "$env_file" || error "Failed to create environment file"
    success "Environment file '$env_file' created"
    sed -i "s/TELEGRAM_WEBHOOK_HOST=.*/TELEGRAM_WEBHOOK_HOST=https:\/\/$instance_name.morebot.top/" "$env_file"
    sed -i "s/DATABASE_USERNAME=.*/DATABASE_USERNAME=${SCRIPT_NAME}_$instance_name/" "$env_file"
    sed -i "s/DATABASE_NAME=.*/DATABASE_NAME=${SCRIPT_NAME}_$instance_name/" "$env_file"
    sed -i "s/DATABASE_PASSWORD=.*/DATABASE_PASSWORD=$instance_pass/" "$env_file"
    success "PostgreSQL credentials set in '$env_file'"
}



subscription_install() {
    log "Starting subscription installation instance '$1' branch '$2'..."
    # ask sure confirmation
    ask_confirmation "subscription installation"
    # check instance name
    check_not_exists "$1"
    # generate instance name
    local instance_name="$1"
    # check branch name
    local branch_name="$2"
    check_branch_name "$branch_name"
    # create directory
    directory_create "$instance_name"
    # clone repo with custom branch
    git_clone "$instance_name" "$branch_name"
    # create postgres user, password, db
    local instance_pass="$(openssl rand -base64 12)"
    postgres_create "$instance_name" "$instance_pass"
    log "PostgreSQL password for user '$instance_name': $instance_pass"
    # setup env
    subscription_create_env "$instance_name" "$instance_pass"
    subscription_show_env "$instance_name"
    # create service
    service_create "$instance_name"
    # start service
    service_start "$instance_name"
    success "Subscription '$instance_name' installation completed"
}
subscription_update() {
    log "Starting subscription update instance '$1' branch '$2'..."
    # ask sure confirmation
    ask_confirmation "subscription update"
    # check instance name
    check_instance_name "$1"
    # check branch name
    local branch_name="$2"
    check_branch_name "$branch_name"
    # stop service
    service_stop "$1"
    # pull latest changes custom branch
    git_update "$1" "$branch_name"
    # start service
    service_start "$1"
}
subscription_remove() {
    log "Starting subscription removal instance '$1'..."
    # ask sure confirmation
    ask_confirmation "subscription removal"
    # check instance name
    check_instance_name "$1"
    # stop service
    service_stop "$1"
    # drop db, user
    postgres_drop "$1"
    # remove service
    service_remove "$1"
    # remove directory
    directory_remove "$1"

}
subscription_status() {
    # check service status
    local instance_name="$1"
    check_instance_name "$instance_name"
    service_status "$instance_name"
}
subscription_start() {
    # start service
    local instance_name="$1"
    check_instance_name "$instance_name"
    service_start "$instance_name"
}
subscription_stop() {
    # stop service
    local instance_name="$1"
    check_instance_name "$instance_name"
    service_stop "$instance_name"
}
subscription_logs() {
    # show service logs
    local instance_name="$1"
    check_instance_name "$instance_name"
    local line_count="${2:-20}"
    if ! [[ "$line_count" =~ ^[0-9]+$ ]]; then
        error "Line count must be a valid number"
        return 1
    fi
    local log_file="$INSTALL_BASE_DIR/$instance_name/$instance_name.log"
    if [[ ! -f "$log_file" ]]; then
        error "Log file '$log_file' does not exist"
    fi
    log "Showing logs for instance '$instance_name' (Press Ctrl+C to exit)"
    tail -n "$line_count" -f "$log_file" || error "Failed to read log file"
}


subscription_update_all() {
    log "Starting update for all subscriptions..."
    # ask sure confirmation
    ask_confirmation "updating all subscriptions"
    if [[ ! -d "$INSTALL_BASE_DIR" ]]; then
        error "Installation base directory '$INSTALL_BASE_DIR' does not exist"
        return 1
    fi
    
    local branch_name="$1"
    if [[ -z "$branch_name" ]]; then
        error "Branch name is required for updating all subscriptions"
    fi
    check_branch_name "$branch_name" 

    local instances=()
    while IFS= read -r -d $'\0' dir; do
        instances+=("$(basename "$dir")")
    done < <(find "$INSTALL_BASE_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    if [[ ${#instances[@]} -eq 0 ]]; then
        warn "No subscriptions found in '$INSTALL_BASE_DIR'"
        return
    fi

    for instance in "${instances[@]}"; do
        log "Updating subscription '$instance'"
        if systemctl is-active --quiet "${SCRIPT_NAME}_$instance"; then
            service_stop "$instance"
            git_update "$instance" "$branch_name"
            service_start "$instance"
            success "Subscription '$instance' updated"
        else
            warn "Subscription '$instance' is not running. Skipping update."
        fi
    done
    success "All subscriptions updated"
}

subscription_import_db() {
    local instance_name="$1"
    local sql_file="$2"
    
    # Check instance exists
    check_instance_name "$instance_name"
    
    # Check SQL file exists
    if [[ -z "$sql_file" ]]; then
        error "SQL file path is required"
    fi
    
    if [[ ! -f "$sql_file" ]]; then
        error "SQL file '$sql_file' does not exist"
    fi
    
    # Get database credentials from env file
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    local env_file="$instance_dir/.env"
    
    if [[ ! -f "$env_file" ]]; then
        error "Environment file '$env_file' does not exist"
    fi
    
    # Extract database credentials
    local db_name=$(grep "DATABASE_NAME=" "$env_file" | awk -F= '{print $2}')
    local db_user=$(grep "DATABASE_USERNAME=" "$env_file" | awk -F= '{print $2}')
    local db_pass=$(grep "DATABASE_PASSWORD=" "$env_file" | awk -F= '{print $2}')    

    if [[ -z "$db_name" || -z "$db_user" || -z "$db_pass" ]]; then
        error "Failed to extract database credentials from environment file"
    fi
    
    # Ask for confirmation
    ask_confirmation "importing SQL file to database '$db_name' (current database will be dropped and recreated)"
    
    # Stop service if running
    if systemctl is-active --quiet "${SCRIPT_NAME}_$instance_name"; then
        log "Stopping service before import..."
        service_stop "$instance_name"
        local was_running=true
    fi
    
    # Drop and recreate database using postgres user
    log "Dropping and recreating database '$db_name'..."
    
    # Drop existing connections and then drop database (as postgres user)
    sudo -u postgres psql -c "
        SELECT pg_terminate_backend(pg_stat_activity.pid) 
        FROM pg_stat_activity 
        WHERE pg_stat_activity.datname = '$db_name' 
        AND pid <> pg_backend_pid();
    " || warn "Failed to terminate existing connections"
    
    # Drop and recreate database (as postgres user)
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $db_name;" || error "Failed to drop database"
    sudo -u postgres psql -c "CREATE DATABASE $db_name OWNER $db_user;" || error "Failed to create database"
    
    # Grant necessary privileges
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $db_name TO $db_user;" || warn "Failed to grant privileges"
    
    success "Database '$db_name' recreated successfully"
    
    # Import SQL file using the database user
    log "Importing SQL file '$sql_file' to database '$db_name'..."
    
    if PGPASSWORD="$db_pass" psql -h localhost -U "$db_user" -d "$db_name" -f "$sql_file"; then
        success "SQL file imported successfully to database '$db_name'"
    else
        error "Failed to import SQL file to database '$db_name'"
    fi
    
    # Start service if it was running
    if [[ "$was_running" == "true" ]]; then
        log "Starting service after import..."
        service_start "$instance_name"
    fi
}

### Service management functions
service_create() {
    # create systemd service file
    local instance_name="$1"
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    local service_file="/etc/systemd/system/${SCRIPT_NAME}_$instance_name.service"
    if [[ -f "$service_file" ]]; then
        error "Service file '$service_file' already exists. It will be replaced."
    fi
    log "Creating systemd service file '$service_file'"
    cat > "$service_file" <<EOF
[Unit]
Description=$SCRIPT_NAME Service (Instance: $instance_name)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$instance_dir
ExecStartPre=uv run alembic upgrade head
ExecStart=uv run main.py
Restart=always
RestartSec=3
TimeoutStopSec=3
KillMode=control-group
KillSignal=SIGKILL
StandardOutput=append:$instance_dir/$instance_name.log
StandardError=append:$instance_dir/$instance_name.log

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload || error "Failed to reload systemd daemon"
    systemctl enable "${SCRIPT_NAME}_$instance_name" || error "Failed to enable service"
    success "Systemd service file '$service_file' created and enabled"
}

service_start() {
    # start service
    local instance_name="$1"
    if [[ ! -f "/etc/systemd/system/${SCRIPT_NAME}_$instance_name.service" ]]; then
        error "Service '${SCRIPT_NAME}_$instance_name' does not exist"
    fi
    log "Starting service '${SCRIPT_NAME}_$instance_name'"
    systemctl start "${SCRIPT_NAME}_$instance_name" || error "Failed to start service"
    success "Service '${SCRIPT_NAME}_$instance_name' started"
}

service_stop() {
    # stop service
    local instance_name="$1"
    if [[ ! -f "/etc/systemd/system/${SCRIPT_NAME}_$instance_name.service" ]]; then
        error "Service '${SCRIPT_NAME}_$instance_name' does not exist"
    fi
    log "Stopping service '${SCRIPT_NAME}_$instance_name'"
    systemctl stop "${SCRIPT_NAME}_$instance_name" || error "Failed to stop service"
    success "Service '${SCRIPT_NAME}_$instance_name' stopped"
}

service_status() {
    # check service status
    local instance_name="$1"
    if [[ ! -f "/etc/systemd/system/${SCRIPT_NAME}_$instance_name.service" ]]; then
        error "Service '${SCRIPT_NAME}_$instance_name' does not exist"
    fi
    local status=$(systemctl is-active "$service_name" 2>/dev/null)
    if [[ "$status" == "active" ]]; then
        success "Service '${SCRIPT_NAME}_$instance_name' is running"
    else
        warn "Service '${SCRIPT_NAME}_$instance_name' is not running"
    fi
}

service_remove() {
    # remove service
    local instance_name="$1"
    local service_file="/etc/systemd/system/${SCRIPT_NAME}_$instance_name.service"
    if [[ ! -f "$service_file" ]]; then
        warn "Service file '$service_file' does not exist"
        return
    fi
    log "Stopping and disabling service '${SCRIPT_NAME}_$instance_name'"
    systemctl stop "${SCRIPT_NAME}_$instance_name" || warn "Failed to stop service"
    systemctl disable "${SCRIPT_NAME}_$instance_name" || warn "Failed to disable service"
    rm -f "$service_file" || error "Failed to remove service file"
    systemctl daemon-reload || error "Failed to reload systemd daemon"
    success "Service '${SCRIPT_NAME}_$instance_name' removed"
}

### script management functions
script_install() {
    local script_path="/usr/local/bin/$SCRIPT_NAME"
    local script_url="https://raw.githubusercontent.com/$USERNAME/$SCRIPT_NAME/master/install.sh"
    
    ### check if script exists
    if [[ -f "$script_path" ]]; then
        warn "$SCRIPT_NAME script already exists. It will be replaced."
        log "Removing existing script..."
        rm -f "$script_path"
        success "Existing script removed"
    fi

    ### Download the script
    log "Installing $SCRIPT_NAME script..."    
    curl -sSLH "Authorization: token $GITHUB_TOKEN" -o "$script_path" "$script_url" || {
        error "Failed to download the script (with token)"
    }
    
    ### Verify the downloaded script
    if [[ ! -s "$script_path" ]]; then
        error "Downloaded script is empty or invalid"
    fi
    
    ### Set execute permissions
    chmod +x "$script_path" || error "Failed to set execute permissions"
    
    ### Verify installation
    if [[ -x "$script_path" ]]; then
        success "$SCRIPT_NAME script successfully installed in $script_path"
        echo "You can now run it with: $SCRIPT_NAME"
    else
        error "Installation verification failed"
    fi
}
script_remove() {
    local script_path="/usr/local/bin/$SCRIPT_NAME"

    ### Check if script exists    
    if [[ -f "$script_path" ]]; then
        log "Removing $SCRIPT_NAME script..."
        rm -f "$script_path" || error "Failed to remove the script"
        success "$SCRIPT_NAME script removed from $script_path"
    else
        warn "$SCRIPT_NAME script not found at $script_path"
    fi
}

### git functions
git_clone() {
    ### Clone the repository with a specific branch
    local instance_name="$1"
    local instance_dir="${INSTALL_BASE_DIR}/$instance_name"
    if [[ ! -d "$instance_dir" ]]; then
        error "Directory '$instance_dir' does not exist"
    fi
    local branch_name="$2"
    log "Cloning repository branch '$branch_name' into '$instance_dir'"
    git clone -b "$branch_name" "https://${GITHUB_TOKEN}@${REPO_URL#https://}" "$instance_dir" || error "Failed to clone repository"
    success "Repository cloned into '$instance_dir'"
}
git_update() {
    ### Update the repository
    local instance_name="$1"
    local instance_dir="${INSTALL_BASE_DIR}/$instance_name"
    if [[ ! -d "$instance_dir" ]]; then
        error "Directory '$instance_dir' does not exist"
    fi
    local branch_name="$2"
    log "Updating repository in '$instance_name'"
    cd "$instance_dir" || error "Failed to access directory '$instance_name'"
    git reset --hard HEAD || error "Failed to reset local changes"
    git fetch --all || error "Failed to fetch updates"
    git checkout "$branch_name" || error "Failed to checkout branch '$branch_name'"
    git reset --hard "origin/$branch_name" || error "Failed to reset to latest commit on branch '$branch_name'"
    success "Repository in '$instance_name' updated"
}

### PostgreSQL functions
postgres_create() {
    # create postgres user, password, db
    local instance_name="$1"
    local db_pass="$2"
    local db_user="${SCRIPT_NAME}_$instance_name"
    local db_name="${SCRIPT_NAME}_$instance_name"
    log "Creating PostgreSQL user '$db_user' and database '$db_name'"
    sudo -u postgres psql -p 5432 -c "CREATE USER $db_user WITH PASSWORD '$db_pass';" || error "Failed to create PostgreSQL user"
    sudo -u postgres psql -p 5432 -c "CREATE DATABASE $db_name OWNER $db_user;" || error "Failed to create PostgreSQL database"
    success "PostgreSQL user '$db_user' and database '$db_name' created"
}
postgres_drop() {
    # drop db, user
    local instance_name="$1"
    local db_user="${SCRIPT_NAME}_$instance_name"
    local db_name="${SCRIPT_NAME}_$instance_name"
    log "Dropping PostgreSQL database '$db_name' and user '$db_user'"
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $db_name;" || warn "Failed to drop database '$db_name'"
    sudo -u postgres psql -c "DROP USER IF EXISTS $db_user;" || warn "Failed to drop user '$db_user'"
    success "PostgreSQL database '$db_name' and user '$db_user' dropped"
}

### directory functions
directory_create() {
    local instance_name="$1"
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    log "Checking directory '$instance_dir'"
    if [[ -d "$instance_dir" ]]; then
        error "Directory '$instance_dir' already exists"
    fi
    log "Creating directory '$instance_dir'"
    mkdir -p "$instance_dir" || error "Failed to create directory '$instance_dir'"
    success "Directory '$instance_dir' created"
}
directory_remove() {
    local instance_name="$1"
    local instance_dir="$INSTALL_BASE_DIR/$instance_name"
    log "Checking directory '$instance_dir'"
    if [[ ! -d "$instance_dir" ]]; then
        warn "Directory '$instance_dir' does not exist"
        return
    fi
    log "Removing directory '$instance_dir'"
    rm -rf "$instance_dir" || error "Failed to remove directory '$instance_dir'"
    success "Directory '$instance_dir' removed"
}


### extra functions
ask_confirmation() {
    operation_description="$1"
    read -p "Are you sure you want to proceed with $operation_description? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        warn "Operation '$operation_description' cancelled"
        exit 0
    fi
}

case "$1" in
    install)
        subscription_install "$2" "$3"
        ;;
    update)
        subscription_update "$2" "$3"
        subscription_logs "$2"
        ;;
    remove)
        subscription_remove "$2"
        ;;
    status)
        subscription_status "$2"
        ;;
    start)
        subscription_start "$2"
        subscription_logs "$2"
        ;;
    stop)
        subscription_stop "$2"
        ;;
    restart)
        subscription_stop "$2"
        subscription_start "$2"
        subscription_logs "$2"
        ;;
    logs)
        subscription_logs "$2" "$3"
        ;;
    env)
        subscription_show_env "$2"
        ;;
    import)
        subscription_import_db "$2" "$3"
        subscription_logs "$2"
        ;;
    update-all)
        subscription_update_all "$2"
        ;;
    script-install)
        script_install
        ;;
    script-update)
        script_install
        ;;
    script-remove)
        script_remove
        ;;
    help)
        ### Display help message
        echo "Script Management for $SCRIPT_NAME"
        echo
        echo "Commands:"
        echo "  install            Install a new subscription"
        echo "  update             Update an existing subscription"
        echo "  remove             Remove an existing subscription"
        echo "  status             Check the status of a subscription"
        echo "  start              Start a subscription"
        echo "  stop               Stop a subscription"
        echo "  restart            Restart a subscription"
        echo "  logs               View logs of a subscription"
        echo "  env                Edit the .env file of a subscription"
        echo "  import             Import a SQL file into a subscription's database"
        echo
        echo "  script-install     Install or update the $SCRIPT_NAME script"
        echo "  script-update      Install or update the $SCRIPT_NAME script"
        echo "  script-remove      Remove the $SCRIPT_NAME script"
        echo "  help               Show this help message"
        ;;
    *)
        error "Invalid command. Use '$SCRIPT_NAME help' for full usage instructions."
        ;;
esac