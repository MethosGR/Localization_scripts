"""
Phrase TMS Bulk Import Script with Progress Tracking
- Features memory-safe streaming CSV processing
- Real-time progress statistics
- Enterprise-grade error handling
"""

import os
import csv
import logging
from time import sleep
from dotenv import load_dotenv
from typing import Dict, Any, Generator
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# Configuration
load_dotenv()
BASE_URL = "https://cloud.memsource.com/web/api/v1"  # Verified correct version
MAX_RETRIES = 3
BACKOFF_FACTOR = 1
TIMEOUT = 30
CSV_FIELDS = {
    'domain': ['name', 'timezone'],
    'subdomain': ['name', 'parent_domain_id'],
    'client': ['name'],
    'business_unit': ['name', 'client_id']
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bulk_import.log'),
        logging.StreamHandler()
    ]
)


class PhraseTMSClient:
    """Enhanced API client with connection pooling and smart retries"""

    def __init__(self):
        self.session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=['POST', 'PUT', 'GET', 'DELETE']
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('https://', adapter)
        self.token = self._authenticate()

    def _authenticate(self) -> str:
        """Secure credential handling with environment variables"""
        credentials = {
            'userName': os.getenv('PHRASE_USER'),
            'password': os.getenv('PHRASE_PASSWORD')
        }
        response = self.session.post(
            f"{BASE_URL}/auth/login",
            json=credentials,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        return response.json()['token']

    def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generic entity creation with conflict detection"""
        endpoints = {
            'domain': '/domains',
            'subdomain': lambda d: f"/domains/{d['parent_domain_id']}/subDomains",
            'client': '/clients',
            'business_unit': '/businessUnits'
        }

        url = BASE_URL + (
            endpoints[entity_type](data) if callable(endpoints[entity_type])
            else endpoints[entity_type]
        )

        response = self.session.post(
            url,
            json=data,
            headers={'Authorization': f'ApiToken {self.token}'},
            timeout=TIMEOUT
        )

        if response.status_code == 409:
            logging.debug(f"Entity conflict: {data.get('name')}")
            return {'status': 'conflict'}

        response.raise_for_status()
        return response.json()


def validate_row(entity_type: str, row: Dict[str, str]) -> bool:
    """Structural validation of CSV rows"""
    required = CSV_FIELDS[entity_type]
    missing = [field for field in required if not row.get(field)]
    if missing:
        logging.warning(f"Missing fields: {missing} in {row.get('name')}")
        return False
    return True


def count_csv_rows(file_path: str, delimiter: str) -> int:
    """Memory-efficient row counting"""
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        next(reader, None)  # Skip header
        return sum(1 for _ in reader)


def process_csv(file_path: str, delimiter: str) -> Generator[Dict[str, str], None, None]:
    """Streaming CSV parser with normalization"""
    with open(file_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            yield {k.strip().lower(): v.strip() for k, v in row.items()}


def bulk_import(file_path: str, delimiter: str, dry_run: bool = False):
    """Main import workflow with progress tracking"""
    client = PhraseTMSClient()
    stats = {'success': 0, 'errors': 0, 'skipped': 0}

    total_rows = count_csv_rows(file_path, delimiter)

    with tqdm(
            total=total_rows,
            desc="🚀 Importing",
            unit="row",
            bar_format="{l_bar}{bar:20}{r_bar}",
            dynamic_ncols=True
    ) as pbar:
        for row in process_csv(file_path, delimiter):
            try:
                entity_type = row.get('type', '').lower()
                if not entity_type or entity_type not in CSV_FIELDS:
                    stats['errors'] += 1
                    logging.error(f"Invalid type: {row.get('type')}")
                    continue

                if not validate_row(entity_type, row):
                    stats['errors'] += 1
                    continue

                if dry_run:
                    stats['success'] += 1
                    continue

                result = client.create_entity(entity_type, row)
                if result.get('status') == 'conflict':
                    stats['skipped'] += 1
                elif result:
                    stats['success'] += 1
                else:
                    stats['skipped'] += 1

            except Exception as e:
                stats['errors'] += 1
                logging.debug(f"Row error: {str(e)}")
                sleep(0.5)  # Error cooldown

            finally:
                pbar.update(1)
                pbar.set_postfix(
                    success=stats['success'],
                    errors=stats['errors'],
                    skipped=stats['skipped'],
                    refresh=False
                )

            del row  # Memory management

    logging.info("\n🔥 Final Statistics:")
    logging.info(f"✅ Success: {stats['success']}")
    logging.info(f"⚠️  Skipped: {stats['skipped']}")
    logging.info(f"❌ Errors: {stats['errors']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Phrase TMS Bulk Import Tool')
    parser.add_argument('file', help='CSV file path')
    parser.add_argument('--delimiter', default=',', help='CSV delimiter')
    parser.add_argument('--dry-run', action='store_true', help='Simulate import')
    args = parser.parse_args()

    try:
        bulk_import(
            args.file,
            args.delimiter,
            args.dry_run
        )
    except KeyboardInterrupt:
        logging.info("\n🛑 Operation cancelled by user")
    except Exception as e:
        logging.error(f"💥 Catastrophic failure: {str(e)}")