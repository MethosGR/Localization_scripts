import requests
import time
import argparse
from datetime import datetime

# Constants
PHRASE_API_BASE_URL = "https://api.phrase.com/v2"
USER_LIMIT = 150  # Maximum allowed seats
CHECK_INTERVAL_SECONDS = 86400  # Check interval (e.g., once per day)


# Helper functions
def get_headers(api_token):
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def get_projects(api_token):
    """Fetch all projects."""
    url = f"{PHRASE_API_BASE_URL}/projects"
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


def remove_excess_users(api_token, filter_timestamp):
    """Remove newly-provisioned users across all projects to stay within the user limit."""
    projects = get_projects(api_token)
    if not projects:
        print("No projects found or error fetching projects.")
        return

    for project in projects:
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
            print(
                f"Removing {excess_user_count} users from project {project_id} to stay within the limit of {USER_LIMIT}.")
            for user in users[:excess_user_count]:
                try:
                    remove_user(api_token, project_id, user['id'])
                except KeyError as e:
                    print(f"Error removing user from project {project_id}: Missing key {e}")
        else:
            print(f"User count for project {project_id} is within the limit. No action needed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Phrase members.")
    parser.add_argument("account_id", help="The Phrase account ID.")
    parser.add_argument("api_token", help="Your Phrase API token.")
    parser.add_argument("filter_timestamp", help="Filter members added after this timestamp (YYYY-MM-DDTHH:mm:SS).",
                        type=str)
    args = parser.parse_args()
    filter_timestamp = datetime.strptime(args.filter_timestamp, "%Y-%m-%dT%H:%M:%S")

    while True:
        print(f"Running user cleanup at {datetime.now()}...")
        remove_excess_users(args.api_token, filter_timestamp)
        print(f"Cleanup complete. Next run in {CHECK_INTERVAL_SECONDS / 3600} hours.")
        time.sleep(CHECK_INTERVAL_SECONDS)
