#!/usr/bin/env python3
"""
Demo script: Import bulk taxonomy via API
Shows how to use the /api/import/taxonomy endpoint with a sample JSON

Requirements:
- Backend running at http://localhost:8000
- Admin user credentials (default: admin@wsw.local / admin_password)
"""

import requests
import json
import sys

BASE_URL = 'http://localhost:8000'

# Sample taxonomy structure
SAMPLE_TAXONOMY = {
    'group': {
        'name': 'Technology',
        'code': 'TECH'
    },
    'subgroups': [
        {
            'name': 'Large Cap Tech',
            'code': 'TECH-LC',
            'categories': [
                {
                    'name': 'Cloud Computing',
                    'code': 'TECH-LC-CLOUD',
                    'asset_type': 'equity',
                    'assets': [
                        {'symbol': 'MSFT', 'name': 'Microsoft Corporation'},
                        {'symbol': 'ORCL', 'name': 'Oracle Corporation'},
                        {'symbol': 'CRM', 'name': 'Salesforce Inc.'},
                    ]
                },
                {
                    'name': 'Software Services',
                    'code': 'TECH-LC-SOFT',
                    'asset_type': 'equity',
                    'assets': [
                        {'symbol': 'SAP', 'name': 'SAP SE'},
                        {'symbol': 'NOW', 'name': 'ServiceNow Inc.'},
                    ]
                }
            ]
        },
        {
            'name': 'Semiconductors',
            'code': 'TECH-SEMI',
            'categories': [
                {
                    'name': 'Chip Designers',
                    'code': 'TECH-SEMI-DES',
                    'asset_type': 'equity',
                    'assets': [
                        {'symbol': 'NVDA', 'name': 'NVIDIA Corporation'},
                        {'symbol': 'QCOM', 'name': 'Qualcomm Inc.'},
                        {'symbol': 'AMD', 'name': 'Advanced Micro Devices'},
                    ]
                }
            ]
        }
    ]
}

def login(email: str, password: str) -> str:
    """Login to backend and return access token"""
    response = requests.post(
        f'{BASE_URL}/api/auth/login',
        json={'email': email, 'password': password}
    )
    
    if response.status_code != 200:
        print(f'❌ Login failed: {response.status_code}')
        print(f'   {response.text}')
        sys.exit(1)
    
    data = response.json()
    token = data.get('access_token')
    print(f'✅ Logged in as {email}')
    return token

def import_taxonomy(token: str, taxonomy: dict) -> dict:
    """Import taxonomy using admin token"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.post(
        f'{BASE_URL}/api/import/taxonomy',
        headers=headers,
        json=taxonomy
    )
    
    if response.status_code != 200:
        print(f'❌ Import failed: {response.status_code}')
        print(f'   {response.text}')
        sys.exit(1)
    
    return response.json()

def print_results(result: dict) -> None:
    """Pretty print import results"""
    print('\n📊 Import Results:')
    print(f'   📦 Groups: {result.get("groups_created", 0)} created, {result.get("groups_updated", 0)} updated')
    print(f'   📁 Subgroups: {result.get("subgroups_created", 0)} created, {result.get("subgroups_updated", 0)} updated')
    print(f'   📂 Categories: {result.get("categories_created", 0)} created, {result.get("categories_updated", 0)} updated')
    print(f'   💰 Assets: {result.get("assets_created", 0)} created, {result.get("assets_updated", 0)} updated')
    print(f'   🔗 Links: {result.get("links_created", 0)} created')
    
    errors = result.get('errors', [])
    if errors:
        print(f'\n⚠️  Errors ({len(errors)}):')
        for error in errors:
            print(f'   - {error}')

def main():
    print('🚀 WSW Bulk Import Demo\n')
    
    # Step 1: Login
    print('Step 1: Authenticating...')
    email = 'admin@wsw.local'
    password = 'admin_password'
    token = login(email, password)
    
    # Step 2: Show sample taxonomy
    print(f'\nStep 2: Preparing import payload...')
    print(f'   📋 Taxonomy: {SAMPLE_TAXONOMY["group"]["name"]}')
    print(f'   └─ {len(SAMPLE_TAXONOMY["subgroups"])} subgroups')
    for sg in SAMPLE_TAXONOMY['subgroups']:
        total_assets = sum(len(cat.get('assets', [])) for cat in sg.get('categories', []))
        print(f'      └─ {sg["name"]} ({total_assets} assets across {len(sg.get("categories", []))} categories)')
    
    # Step 3: Import
    print(f'\nStep 3: Importing taxonomy...')
    result = import_taxonomy(token, SAMPLE_TAXONOMY)
    
    # Step 4: Display results
    print_results(result)
    
    print(f'\n✅ Demo completed successfully!')
    print(f'\n💡 Next steps:')
    print(f'   1. Visit http://localhost:3000 to see the imported assets in the Universe page')
    print(f'   2. Select category "Cloud Computing" or "Semiconductors"')
    print(f'   3. Use pagination controls to browse the assets')
    print(f'   4. Import custom taxonomies by creating a JSON file and using the web UI')

if __name__ == '__main__':
    main()
