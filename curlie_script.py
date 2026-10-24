import os
import json
import csv
from collections import defaultdict
from pathlib import Path

# Configuration
DATA_DIR = "./curlie_data"
OUTPUT_DIR = "./curlie_json"
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Mapping of categories to their TSV/CSV files based on README
CATEGORY_FILE_MAPPING = {
    "Arts": ["rdf-Arts"],
    "Business": ["rdf-Business"],
    "Computers": ["rdf-Top"],
    "Games": ["rdf-Top"],
    "Health": ["rdf-Top"],
    "Home": ["rdf-Top"],
    "News": ["rdf-Top"],
    "Recreation": ["rdf-Top"],
    "Reference": ["rdf-Top"],
    "Science": ["rdf-Top"],
    "Shopping": ["rdf-Top"],
    "Sports": ["rdf-Top"],
    "Society": ["rdf-Society"],
    "Kids and Teens": ["rdf-KT"],
    "Regional": ["rdf-Regional", "rdf-NorthAmerica", "rdf-Europe"]
}

def estimate_json_size(data):
    return len(json.dumps(data, ensure_ascii=False).encode('utf-8'))

def parse_categories_file(filepath):
    categories = {}
    
    if not os.path.exists(filepath):
        alt_filepath = filepath.replace('.tsv', '.csv')
        if os.path.exists(alt_filepath):
            filepath = alt_filepath
        else:
            print(f"  ⚠️ WARNING: File not found: {filepath}")
            return categories
            
    with open(filepath, 'r', encoding='utf-8') as f:
        sample = f.read(1024)
        delimiter = '\t' if '\t' in sample else ','
        
    rows_parsed = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if len(row) >= 4:
                category_id = row[0].strip()
                
                if category_id.lower() in ["category id", "id"]:
                    continue
                
                full_path = row[1].strip()
                num_entries = row[2].strip()
                description = row[3].strip() if len(row) > 3 else ""
                
                title = full_path.split('/')[-1].replace('_', ' ') if '/' in full_path else full_path.replace('_', ' ')
                
                categories[category_id] = {
                    'id': category_id,
                    'full_path': full_path,
                    'title': title,
                    'description': description,
                    'num_entries': int(num_entries) if num_entries.isdigit() else 0,
                    'subcategories': [],
                    'links': []
                }
                rows_parsed += 1
                
    print(f"    ✅ Parsed {rows_parsed} categories from {os.path.basename(filepath)}")
    return categories

def parse_sites_file(filepath):
    sites_by_category = defaultdict(list)
    
    if not os.path.exists(filepath):
        alt_filepath = filepath.replace('.tsv', '.csv')
        if os.path.exists(alt_filepath):
            filepath = alt_filepath
        else:
            print(f"  ️ WARNING: File not found: {filepath}")
            return sites_by_category
            
    with open(filepath, 'r', encoding='utf-8') as f:
        sample = f.read(1024)
        delimiter = '\t' if '\t' in sample else ','
        
    rows_parsed = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if len(row) >= 4:
                url = row[0].strip()
                
                if url.lower() in ["url", "website url"]:
                    continue
                
                title = row[1].strip()
                description = row[2].strip()
                category_id = row[3].strip()
                
                sites_by_category[category_id].append({
                    'url': url,
                    'title': title,
                    'description': description
                })
                rows_parsed += 1
                
    print(f"    ✅ Parsed {rows_parsed} sites from {os.path.basename(filepath)}")
    return sites_by_category

def build_category_tree(all_categories, all_sites):
    categories_by_path = {}
    for cat_id, cat_data in all_categories.items():
        full_path = cat_data['full_path']
        categories_by_path[full_path] = cat_data
    
    for full_path, cat_data in categories_by_path.items():
        parts = full_path.rsplit('/', 1)
        if len(parts) > 1:
            parent_path = parts[0]
            if parent_path in categories_by_path:
                parent_cat = categories_by_path[parent_path]
                parent_cat['subcategories'].append({
                    'id': cat_data['id'],
                    'full_path': full_path,
                    'title': cat_data['title']
                })
    
    for cat_id, cat_data in all_categories.items():
        if cat_id in all_sites:
            cat_data['links'] = all_sites[cat_id]
    
    return all_categories

def filter_category_by_name(all_categories, category_name):
    filtered = {}
    
    # Curlie uses underscores instead of spaces in paths (e.g., Kids_and_Teens)
    underscored_name = category_name.replace(' ', '_')
    
    if category_name == "Regional":
        prefixes = [
            "Top/Regional", "Regional", "Top/NorthAmerica", "NorthAmerica", 
            "Top/Europe", "Europe", "Top/Regional_", "Regional_",
            "Top/North_America", "North_America", "Top/Europe_", "Europe_"
        ]
    elif category_name == "Kids and Teens":
        prefixes = ["Kids_and_Teens", "Top/Kids_and_Teens", "KT", "Top/KT"]
    else:
        prefixes = [
            f"Top/{category_name}", category_name, 
            f"Top/{underscored_name}", underscored_name
        ]
    
    for cat_id, cat_data in all_categories.items():
        full_path = cat_data['full_path']
        
        # Check if the full_path exactly matches or starts with prefix + '/' 
        # (This prevents "Top/Art" from accidentally matching "Top/Artificial_Intelligence")
        for prefix in prefixes:
            if full_path == prefix or full_path.startswith(prefix + '/'):
                filtered[cat_id] = cat_data
                break
            
    # DEBUG: If 0 found, print the actual paths so we know exactly what to fix
    if not filtered and all_categories:
        sample_paths = [cat_data['full_path'] for cat_data in list(all_categories.values())[:5]]
        print(f"   DEBUG: Filter found 0 categories. Sample full_paths in file: {sample_paths}")
        
    return filtered

def split_into_size_limited_files(category_name, categories_data):
    if not categories_data:
        print(f"  ⚠️ WARNING: No data to split for {category_name}")
        return []

    files_created = []
    current_file_data = {}
    current_file_size = 0
    file_index = 1
    
    sorted_categories = sorted(categories_data.items(), key=lambda x: x[1]['full_path'])
    
    for cat_id, cat_data in sorted_categories:
        item_size = estimate_json_size({cat_id: cat_data})
        
        if current_file_size + item_size > MAX_FILE_SIZE_BYTES and current_file_data:
            filename = f"{category_name.lower().replace(' ', '-')}_part{file_index}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(current_file_data, f, indent=2, ensure_ascii=False)
            
            files_created.append({
                'filename': filename,
                'filepath': filepath,
                'categories_count': len(current_file_data),
                'size_mb': round(current_file_size / (1024 * 1024), 2)
            })
            
            current_file_data = {}
            current_file_size = 0
            file_index += 1
        
        current_file_data[cat_id] = cat_data
        current_file_size += item_size
    
    if current_file_data:
        filename = f"{category_name.lower().replace(' ', '-')}_part{file_index}.json"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(current_file_data, f, indent=2, ensure_ascii=False)
        
        files_created.append({
            'filename': filename,
            'filepath': filepath,
            'categories_count': len(current_file_data),
            'size_mb': round(current_file_size / (1024 * 1024), 2)
        })
    
    return files_created

def process_category(category_name, file_prefixes):
    print(f"\n{'='*60}")
    print(f"Processing: {category_name}")
    print(f"Files: {', '.join(file_prefixes)}")
    print(f"{'='*60}")
    
    all_categories = {}
    all_sites = defaultdict(list)
    
    for prefix in file_prefixes:
        cats_file = os.path.join(DATA_DIR, f"{prefix}-s.tsv")
        sites_file = os.path.join(DATA_DIR, f"{prefix}-c.tsv")
        
        print(f"  Parsing categories...")
        categories = parse_categories_file(cats_file)
        all_categories.update(categories)
        
        print(f"  Parsing sites/links...")
        sites = parse_sites_file(sites_file)
        for cat_id, site_list in sites.items():
            all_sites[cat_id].extend(site_list)
    
    print(f"  Building category tree...")
    all_categories = build_category_tree(all_categories, all_sites)
    
    print(f"  Filtering for {category_name}...")
    filtered_categories = filter_category_by_name(all_categories, category_name)
    
    total_links = sum(len(cat['links']) for cat in filtered_categories.values())
    total_subcats = sum(len(cat['subcategories']) for cat in filtered_categories.values())
    
    print(f"  ✅ Found {len(filtered_categories)} categories")
    print(f"  ✅ Total links: {total_links:,}")
    print(f"  ✅ Total subcategory relationships: {total_subcats:,}")
    
    print(f"  Splitting into files (max {MAX_FILE_SIZE_MB}MB each)...")
    files_created = split_into_size_limited_files(category_name, filtered_categories)
    
    return files_created

def create_summary(all_files):
    summary = {
        "generated_at": str(Path.cwd()),
        "max_file_size_mb": MAX_FILE_SIZE_MB,
        "categories": {}
    }
    
    for cat_name, files in all_files.items():
        total_cats = sum(f['categories_count'] for f in files)
        total_size = sum(f['size_mb'] for f in files)
        
        summary["categories"][cat_name] = {
            "files_count": len(files),
            "total_categories": total_cats,
            "total_size_mb": round(total_size, 2),
            "files": [f['filename'] for f in files]
        }
    
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Summary saved to: {summary_path}")
    return summary

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("="*60)
    print("CURLIE DATA PARSER - BULLETPROOF EDITION v3")
    print("="*60)
    print(f"Input directory: {DATA_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Max file size: {MAX_FILE_SIZE_MB}MB")
    print("="*60)
    
    all_files = {}
    
    for category_name, file_prefixes in CATEGORY_FILE_MAPPING.items():
        files = process_category(category_name, file_prefixes)
        all_files[category_name] = files
        
        for f in files:
            print(f"    💾 {f['filename']}: {f['categories_count']} categories, {f['size_mb']}MB")
    
    summary = create_summary(all_files)
    
    print("\n" + "="*60)
    print("PROCESSING COMPLETE")
    print("="*60)
    total_files = sum(len(files) for files in all_files.values())
    total_size = sum(sum(f['size_mb'] for f in files) for files in all_files.values())
    total_categories = sum(sum(f['categories_count'] for f in files) for files in all_files.values())
    
    print(f"Total categories processed: {total_categories:,}")
    print(f"Total files created: {total_files}")
    print(f"Total size: {round(total_size, 2)}MB")
    print(f"Output directory: {OUTPUT_DIR}")
    print("="*60)

if __name__ == "__main__":
    main()