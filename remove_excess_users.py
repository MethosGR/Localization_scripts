import requests
import time
from datetime import datetime, timedelta
from tqdm import tqdm

# Constants
PHRASE_API_BASE_URL = "https://api.phrase.com/v2"
USER_LIMIT = 150  # Maximum allowed seats
START_DATE = datetime(2025, 3, 1, 0, 0, 0)  # Hardcoded starting date for new user addition
RUN_INTERVAL = timedelta(weeks=1)  # Set to run every week after initial run

def get_headers(api_token):
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

def get_projects(api_token, account_id):
    """Fetch all projects for a given account."""
    url = f"{PHRASE_API_BASE_URL}/accounts/{account_id}/projects"
    response = requests.get(url, headers=get_headers(api_token))
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching projects: {response.status_code}, {response.text}")
        return []

def get_users(api_token, project_id):
    """Fetch all users in a project."""
    url = f"{PHRASE_API_BASE_URL}/projects/{project_id}/users"
    response = requests.get(url, headers=get_headers(api_token))
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching users for project {project_id}: {response.status_code}, {response.text}")
        return []

def remove_user(api_token, project_id, user_id):
    """Remove a user by ID from a specific project."""
    url = f"{PHRASE_API_BASE_URL}/projects/{project_id}/users/{user_id}"
    response = requests.delete(url, headers=get_headers(api_token))
    if response.status_code == 204:
        print(f"User {user_id} removed successfully from project {project_id}.")
    else:
        print(f"Error removing user {user_id} from project {project_id}: {response.status_code}, {response.text}")

def remove_excess_users(api_token, account_id, filter_timestamp):
    """Remove newly-provisioned users across all projects to stay within the user limit."""
    projects = get_projects(api_token, account_id)
    if not projects:
        print("No projects found or error fetching projects.")
        return

    for project in tqdm(projects, desc="Processing projects", unit="project"):
        project_id = project['id']
        users = get_users(api_token, project_id)
        if not users:
            print(f"No users found or error fetching users for project {project_id}.")
            continue

        try:
            users = [u for u in users if datetime.strptime(u['created_at'], '%Y-%m-%dT%H:%M:%SZ') > filter_timestamp]
            users.sort(key=lambda x: datetime.strptime(x['created_at'], '%Y-%m-%dT%H:%M:%SZ'), reverse=True)
        except KeyError as e:
            print(f"Error sorting users for project {project_id}: Missing key {e}")
            continue

        excess_user_count = len(users) - USER_LIMIT
        if excess_user_count > 0:
            print(f"Removing {excess_user_count} users from project {project_id} to stay within the limit of {USER_LIMIT}.")
            for user in tqdm(users[:excess_user_count], desc=f"Removing users from {project_id}", unit="user"):
                try:
                    remove_user(api_token, project_id, user['id'])
                except KeyError as e:
                    print(f"Error removing user from project {project_id}: Missing key {e}")
        else:
            print(f"User count for project {project_id} is within the limit. No action needed.")

if __name__ == "__main__":
    api_token = "your_api_token"
    account_id = "your_account_id"
    next_run = START_DATE

    while True:
        current_time = datetime.now()
        if current_time >= next_run:
            print(f"Running user cleanup at {current_time}...")
            remove_excess_users(api_token, account_id, START_DATE)
            print("Cleanup complete.")
            next_run += RUN_INTERVAL
        time.sleep(3600)  # Check every hour if it's time to run again
