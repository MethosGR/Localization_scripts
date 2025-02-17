#!/usr/bin/env python3
import asyncio
from email import message
from math import e
from tkinter import W
import aiohttp
import argparse
import sys
import json
from aiohttp import ClientConnectionError
from tqdm import tqdm
import logging

logging.basicConfig(level=logging.DEBUG)

# Base URL for the Phrase API.
BASE_URL = "https://api.phrase.com/v2"

# --- Hardcoded API token and parent project ID ---
HARD_CODED_API_TOKEN = "abd72e6cfbabe8e14ce518c4c1c762a35c11e945feda5a16c7671167f17e66c0"
# Replace the string below with your actual parent project ID.
HARD_CODED_PARENT_PROJECT_ID = "b030ce2bb69df7f099af17804e846f7a"

# Global HTTP headers.
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ---------------------------
# Helper: Request with Retries for Rate Limiting and Connection Errors
# ---------------------------
async def request_with_retries(session, method, url, **kwargs):
    """
    A helper function to perform an HTTP request with retries if a rate limit (429)
    or connection error is encountered.

    - If the response status is 429, this function reads the 'Retry-After' header
      (if present) or uses an exponential backoff (2^retries seconds) before retrying.
    - If a ClientConnectionError occurs, it will also wait using exponential backoff.
    - Retries up to max_retries times.
    """
    retries = 0
    max_retries = 10
    while retries <= max_retries:
        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status != 429:
                    # Read the response using StreamReader
                    raw_text = await response.content.read()
                    raw_text_decoded = raw_text.decode('utf-8')

                    try:
                        data = json.loads(raw_text_decoded)
                    except json.JSONDecodeError as e:
                        data = {}
                    
                    return response, data
                else:
                    if retries >= max_retries:
                        return response  # Give up after max_retries
                    # Check for a Retry-After header:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = int(retry_after) if retry_after is not None else (2 ** retries)
                    except ValueError:
                        delay = 2 ** retries
                    print(
                        f"[429] Rate limit exceeded, retrying in {delay} seconds... (attempt {retries + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    retries += 1
        except ClientConnectionError as e:
            if retries >= max_retries:
                raise e
            delay = 2 ** retries
            print(
                f"[ConnectionError] Connection closed, retrying in {delay} seconds... (attempt {retries + 1}/{max_retries})")
            await asyncio.sleep(delay)
            retries += 1
    raise Exception(f"Max retries exceeded for URL: {url}")


# ---------------------------
# Utility Functions
# ---------------------------
async def get_all_projects(session, per_page=100):
    """
    Fetch all projects from the Phrase API using pagination.
    Endpoint: GET /projects
    """
    projects = []
    page = 1
    while True:
        url = f"{BASE_URL}/projects"
        params = {"page": page, "per_page": per_page}
        async with session.get(url, headers=HEADERS, params=params) as response:
            print(f"Using API Token: {HEADERS.get('Authorization')}")

            if response.status != 200:
                text = await response.text()
                print(f"Error fetching projects on page {page}: {response.status} - {text}")
                sys.exit(1)
            else:
                print(f"Listing projects - page {page} downloaded")

            # Read the response using StreamReader
            raw_text = await response.content.read()
            raw_text_decoded = raw_text.decode('utf-8')

            try:
                data = json.loads(raw_text_decoded)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                sys.exit(1)

            if not data:
                break  # No more projects.
            projects.extend(data)
            page += 1
    return projects


async def get_all_keys(session, project_id, per_page=100, q_string=""):
    """
    Fetch all keys for a given project using pagination.
    Endpoint: GET /projects/{project_id}/keys
    """
    keys = []
    page = 1
    totalPage = 1

    while totalPage >= page:
        url = f"{BASE_URL}/projects/{project_id}/keys"
        params = {"page": page, "per_page": per_page}

        if q_string:
            params["q"] = q_string  # Add the q_string to the params if it is not empty

        response, data = await request_with_retries(session, "GET", url, headers=HEADERS, params=params)
        
        if response.status != 200:
            text = await response.text()
            print(f"Error fetching keys from project {project_id} on page {page}: {response.status} - {text}")
            sys.exit(1)
        else:
            print(f"Listing keys of project {project_id} - page {page} downloaded")

        pagination_header = response.headers.get("Pagination")
        if pagination_header:
            try:
                pagination_data = json.loads(pagination_header)
                total_pages = pagination_data.get("total_pages_count", 1)
            except json.JSONDecodeError as e:
                print(f"Error decoding pagination header: {e}")
                sys.exit(1)

        if not data:
            break  # No more keys.
        keys.extend(data)
        page += 1
    return keys


async def get_key_detail(session, project_id, key_id, semaphore):
    """
    Fetch detailed information for a specific key.
    Endpoint: GET /projects/{project_id}/keys/{id}

    The detailed response is used to check if the key was created as a link
    (via the 'parent_key_id' field).
    """
    url = f"{BASE_URL}/projects/{project_id}/keys/{key_id}"
    async with semaphore:
        try:
            response, data = await request_with_retries(session, "GET", url, headers=HEADERS)
            if response.status == 200:
                return data
            else:
                print(f"Non 200 response for fetching detail for key {key_id} in project {project_id}")
                return None
        except Exception as e:
            print(f"Error fetching detail for key {key_id} in project {project_id}: {e}")
            return None

async def get_linked_child_keys(session, parent_project_id, parent_key_id):
    """
    Fetch keys that are linked to a parent key.
    Endpoint: GET /projects/{project_id}/keys/{id}/key_links
    """
    url = f"{BASE_URL}/projects/{parent_project_id}/keys/{parent_key_id}/key_links"

    response, data = await request_with_retries(session, "GET", url, headers=HEADERS)

    if response.status == 400:
        return []
    elif response.status != 200:
        text = await response.text()
        print(f"Error fetching existing links for {parent_key_id}")
        sys.exit(1)
    else:
        print(f"List of linked keys to parent key {parent_key_id} downloaded")

    child_key_ids = [child_key['id'] for child_key in data.get('children', [])]
    return child_key_ids

async def create_key_link(session, parent_project_id, parent_key_id, child_key_ids, semaphore):
    """
    Create a key link from the parent's key to the relevant child project keys.

    Endpoint: POST /projects/{parent_project_id}/keys/{parent_key_id}/key_links
    Payload: { "child_key_ids": ["child_key_id1", "child_key_id2"] }

    This call creates a new link between keys in the child projects to the parent project's key.
    """
    url = f"{BASE_URL}/projects/{parent_project_id}/keys/{parent_key_id}/key_links"
    payload = {"child_key_ids": child_key_ids}  # Using the provided child_key_ids array to build the payload
    
    async with semaphore:
        try:
            response, data = await request_with_retries(session, "POST", url, json=payload, headers=HEADERS)
            if response.status != 201:
                if data:
                    print(
                        f"Failed to link parent key '{parent_key_id}' to child keys {', '.join(child_key_ids)}: "
                        f"status {response.status} - {data['message']} - {data['errors'][0]['message']}"

                    )
                else:
                    print(
                        f"Failed to link parent key '{parent_key_id}' to child keys {', '.join(child_key_ids)}: "
                        f"status {response.status}"
                    )
            else:
                print(f"Successfully linked parent key '{parent_key_id}' to child keys {', '.join(child_key_ids)}")
        except Exception as e:
            print(
                f"Exception occurred while linking parent key '{parent_key_id}' to child keys {', '.join(child_key_ids)}: {e}"
            )

# ---------------------------
# Main Function
# ---------------------------
async def main(args):
    # Use a TCPConnector with a lower limit to help control the number of simultaneous connections.
    connector = aiohttp.TCPConnector(limit=args.concurrency_limit)
    async with aiohttp.ClientSession(connector=connector) as session:
        # STEP 1: Fetch all projects.
        print("Fetching all projects...")
        projects = await get_all_projects(session)
        if not projects:
            print("No projects found.")
            sys.exit(1)

        # STEP 2: Hardcode the parent project.
        parent_project_id = HARD_CODED_PARENT_PROJECT_ID
        if not any(proj["id"] == parent_project_id for proj in projects):
            print(f"Hardcoded parent project id '{parent_project_id}' not found among projects.")
            sys.exit(1)
        print(f"Using hardcoded parent project id: {parent_project_id}")

        # STEP 3: Fetch keys from the parent projects.
        print(f"Fetching keys from parent project {parent_project_id}...")
        parent_keys = await get_all_keys(session, parent_project_id)
        
        linked_keys_dict = {}
        for parent_key in parent_keys:
            parent_key_id = parent_key.get("id")
            linked_keys = await get_linked_child_keys(session, parent_project_id, parent_key_id)
            if linked_keys:
                linked_keys_dict[parent_key_id] = linked_keys
        
        print(f"Total keys fetched from parent project: {len(parent_keys)}")

        # STEP 4: Determine child projects (all projects except the parent).
        child_projects = [proj for proj in projects if proj["id"] != parent_project_id]
        print(f"Found {len(child_projects)} child projects.")

        # STEP 5: Schedule key linking tasks for keys not already linked.
        tasks = []
        link_semaphore = asyncio.Semaphore(args.concurrency_limit)
        key_links_map = {}

        for i in range(0, len(parent_keys), 100):
            parent_key_batch = parent_keys[i:i + 100]
            parent_key_names = [parent_key.get("name") for parent_key in parent_key_batch if parent_key.get("name")]
            q_string = "name:" + ",".join(parent_key_names)

            for child_project in child_projects:
                child_project_id = child_project["id"]
                child_keys = await get_all_keys(session, child_project_id, q_string=q_string)
                if child_keys:
                    child_key_map = {child_key["name"]: child_key["id"] for child_key in child_keys}

                    for parent_key in parent_key_batch:
                        parent_key_id = parent_key.get("id")
                        parent_key_name = parent_key.get("name")

                        if not parent_key_id or not parent_key_name:
                            continue

                        child_key_id = child_key_map.get(parent_key_name)
                        if child_key_id:
                           if parent_key_id in linked_keys_dict.keys() and (child_key_id in linked_keys_dict.get(parent_key_id, [])):
                               print(f"{child_key_id} is already linked")
                           elif any(child_key_id in child_ids for child_ids in linked_keys_dict.values()):
                               print(f"{child_key_id} is already linked")
                           else:
                                if parent_key_id not in key_links_map:
                                    key_links_map[parent_key_id] = []
                                key_links_map[parent_key_id].append(child_key_id)
                                print(f"{child_key_id} is added for linking")

        tasks = [create_key_link(session, parent_project_id, parent_key_id, child_key_ids, link_semaphore)
                 for parent_key_id, child_key_ids in key_links_map.items()]


        total_tasks = len(tasks)
        print(f"Scheduling {total_tasks} key link tasks (after excluding existing links)...")
        progress_bar = tqdm(total=total_tasks, desc="Linking keys", unit="link")
        for task in asyncio.as_completed(tasks):
            await task
            progress_bar.update(1)
        progress_bar.close()
        print("All missing key links have been created.")

# ---------------------------
# Entry Point
# ---------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Link keys from a hardcoded parent project to all other (child) projects, excluding already linked keys."
    )
    # The API token argument is optional. If not provided, the hardcoded token is used.
    parser.add_argument("--api-token", required=False,
                        help="Your Phrase API token. If not provided, the hardcoded token will be used.")
    # Lower the default concurrency limit to 10 for less aggressive behavior.
    parser.add_argument("--concurrency-limit", type=int, default=4,
                        help="Maximum concurrent API calls (default: 4).")
    args = parser.parse_args()

    HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Connection": "keep-alive"
    }

    # Set the API token: if provided, use it; otherwise, use the hardcoded token.
    if args.api_token:
        HEADERS["Authorization"] = f"token {args.api_token}"
    else:
        HEADERS["Authorization"] = f"token {HARD_CODED_API_TOKEN}"

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("Execution interrupted by user. Exiting...")
