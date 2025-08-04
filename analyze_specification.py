#!/usr/bin/env python3
"""
Comprehensive analysis script for Azure REST API specifications.
Analyzes TypeSpec projects, folder structure alignment, and generates detailed report.
"""

import os
import json
import glob
import pandas as pd
from pathlib import Path
import yaml
import re

def find_files_with_pattern(directory, pattern):
    """Find all files matching a pattern in directory and subdirectories."""
    matches = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == pattern:
                matches.append(os.path.join(root, file))
    return matches

def find_typespec_projects(spec_path):
    """Find all TypeSpec projects by looking for tspconfig.yaml or main.tsp files."""
    tspconfig_files = find_files_with_pattern(spec_path, 'tspconfig.yaml')
    main_tsp_files = find_files_with_pattern(spec_path, 'main.tsp')
    
    # Combine and deduplicate by directory
    typespec_dirs = set()
    
    for tspconfig in tspconfig_files:
        typespec_dirs.add(os.path.dirname(tspconfig))
    
    for main_tsp in main_tsp_files:
        typespec_dirs.add(os.path.dirname(main_tsp))
    
    return list(typespec_dirs)

def is_management_plane(project_or_file_path):
    """Determine if a TypeSpec project or Swagger file is management plane based on folder name or path."""
    # For TypeSpec projects, check if folder name contains '.Management'
    folder_name = os.path.basename(project_or_file_path)
    if '.Management' in folder_name:
        return True
    
    # For both TypeSpec and Swagger files, check if path contains 'resource-manager'
    if 'resource-manager' in project_or_file_path:
        return True
    
    # If neither condition is met, it's data plane
    return False

def check_folder_structure_v2_compliance(folder_path, spec_base_path):
    """Check if folder follows folder structure v2 strictly."""
    rel_path = os.path.relpath(folder_path, spec_base_path)
    path_parts = rel_path.split(os.sep)
    
    if len(path_parts) < 2:
        return False, f"Path too short: {rel_path}"
    
    # Skip common-types and other shared folders - these are always compliant
    if path_parts[0] in ['common-types']:
        return True, "Shared/common folder - compliant"
    
    org_name = path_parts[0]
    folder_name = os.path.basename(folder_path)
    
    # Check if this folder contains TypeSpec projects
    has_typespec = any(os.path.exists(os.path.join(folder_path, f)) for f in ['tspconfig.yaml', 'main.tsp'])
    
    # Check if this is a stable/preview folder
    is_stable_preview_folder = folder_name.lower() in ['stable', 'preview']
    
    def is_pascal_case(s):
        """Check if string is PascalCase (starts with uppercase, no spaces/special chars except dots)."""
        if not s or not s[0].isupper():
            return False
        # Allow letters, numbers, and dots for namespace pattern
        return all(c.isalnum() or c == '.' for c in s)
    
    def is_valid_namespace_pattern(namespace):
        """Check if namespace follows A.B pattern where A and B are PascalCase."""
        if '.' not in namespace:
            return False
        parts = namespace.split('.')
        if len(parts) != 2:
            return False
        return all(is_pascal_case(part) and '.' not in part for part in parts)
    
    def is_valid_service_name(service_name):
        """Check if service name contains no special characters (only letters, numbers, hyphens)."""
        return all(c.isalnum() or c == '-' for c in service_name)
    
    # STRICT COMPLIANCE RULES - Only exact patterns are compliant:
    
    # Rule 1: TypeSpec project root folders must be EXACTLY in correct location
    if has_typespec:
        if is_management_plane(folder_path):
            # Management plane: MUST be exactly specification/{orgName}/resource-manager/{namespaceName}/{serviceName}
            if len(path_parts) == 4 and path_parts[1] == 'resource-manager':
                namespace_name = path_parts[2]
                service_name = path_parts[3]
                
                # Validate namespace pattern (A.B format with PascalCase)
                if not is_valid_namespace_pattern(namespace_name):
                    return False, f"Non-compliant namespace pattern '{namespace_name}': should be A.B format with PascalCase (e.g., Microsoft.Compute)"
                
                # Validate service name (no special characters)
                if not is_valid_service_name(service_name):
                    return False, f"Non-compliant service name '{service_name}': should not contain special characters"
                
                return True, "Compliant management plane TypeSpec project root"
            else:
                return False, f"Non-compliant management plane TypeSpec structure: {rel_path} (must be exactly specification/{{orgName}}/resource-manager/{{namespaceName}}/{{serviceName}})"
        else:
            # Data plane: MUST be exactly specification/{orgName}/data-plane/{serviceName}
            if len(path_parts) == 3 and path_parts[1] == 'data-plane':
                service_name = path_parts[2]
                
                # Validate service name (no special characters)
                if not is_valid_service_name(service_name):
                    return False, f"Non-compliant service name '{service_name}': should not contain special characters"
                
                return True, "Compliant data plane TypeSpec project root"
            else:
                return False, f"Non-compliant data plane TypeSpec structure: {rel_path} (must be exactly specification/{{orgName}}/data-plane/{{serviceName}})"
    
    # Rule 2: Swagger stable/preview folders must be EXACTLY in correct location
    elif is_stable_preview_folder:
        if 'resource-manager' in rel_path:
            # Management plane: MUST be exactly specification/{orgName}/resource-manager/{namespaceName}/{serviceName}/stable|preview
            if len(path_parts) == 5 and path_parts[1] == 'resource-manager' and path_parts[4] == folder_name:
                namespace_name = path_parts[2]
                service_name = path_parts[3]
                
                # Validate namespace pattern (A.B format with PascalCase)
                if not is_valid_namespace_pattern(namespace_name):
                    return False, f"Non-compliant namespace pattern '{namespace_name}': should be A.B format with PascalCase (e.g., Microsoft.Compute)"
                
                # Validate service name (no special characters)
                if not is_valid_service_name(service_name):
                    return False, f"Non-compliant service name '{service_name}': should not contain special characters"
                
                return True, f"Compliant management plane Swagger {folder_name} folder"
            else:
                return False, f"Non-compliant management plane Swagger {folder_name} structure: {rel_path} (must be exactly specification/{{orgName}}/resource-manager/{{namespaceName}}/{{serviceName}}/{folder_name})"
        elif 'data-plane' in rel_path:
            # Data plane: MUST be exactly specification/{orgName}/data-plane/{serviceName}/stable|preview
            if len(path_parts) == 4 and path_parts[1] == 'data-plane' and path_parts[3] == folder_name:
                service_name = path_parts[2]
                
                # Validate service name (no special characters)
                if not is_valid_service_name(service_name):
                    return False, f"Non-compliant service name '{service_name}': should not contain special characters"
                
                return True, f"Compliant data plane Swagger {folder_name} folder"
            else:
                return False, f"Non-compliant data plane Swagger {folder_name} structure: {rel_path} (must be exactly specification/{{orgName}}/data-plane/{{serviceName}}/{folder_name})"
        else:
            return False, f"Swagger {folder_name} folder not in resource-manager or data-plane structure: {rel_path}"
    
    # If we reach here, it's neither a TypeSpec project root nor a stable/preview folder
    return False, f"Not a TypeSpec project root or Swagger stable/preview folder: {rel_path}"

def find_swagger_files(org_path):
    """Find all Swagger/OpenAPI files in the organization directory."""
    swagger_files = []
    for root, dirs, files in os.walk(org_path):
        # Skip examples directories
        dirs[:] = [d for d in dirs if d.lower() != 'examples']
        
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                # Double check - exclude files that have 'examples' in their path
                if 'examples' not in file_path.lower():
                    swagger_files.append(file_path)
    return swagger_files

def classify_swagger_files(swagger_files, org_path):
    """Classify swagger files as management plane or data plane based on folder path."""
    mgmt_swagger = []
    data_swagger = []
    
    for swagger_file in swagger_files:
        rel_path = os.path.relpath(swagger_file, org_path)
        if 'resource-manager' in rel_path:
            mgmt_swagger.append(swagger_file)
        elif 'data-plane' in rel_path:
            data_swagger.append(swagger_file)
        # If neither, we'll count it as unclassified but not include in mgmt/data counts
    
    return mgmt_swagger, data_swagger

def has_data_plane_swagger(org_path):
    """Check if organization has data plane swagger specifications."""
    data_plane_path = os.path.join(org_path, 'data-plane')
    if not os.path.exists(data_plane_path):
        return False
    
    # Look for swagger files in data-plane directories
    for root, dirs, files in os.walk(data_plane_path):
        # Skip examples directories
        dirs[:] = [d for d in dirs if d.lower() != 'examples']
        
        for file in files:
            if file.endswith('.json') and ('swagger' in file.lower() or 'openapi' in file.lower()):
                return True
    return False

def count_readme_files_in_resource_manager(org_path):
    """Count README.md files in resource-manager folder recursively."""
    rm_path = os.path.join(org_path, 'resource-manager')
    if not os.path.exists(rm_path):
        return 0
    
    readme_files = find_files_with_pattern(rm_path, 'readme.md')
    # Also check for README.md (case insensitive)
    readme_files_upper = find_files_with_pattern(rm_path, 'README.md')
    
    return len(set(readme_files + readme_files_upper))

def is_rpaas_service(org_path):
    """Check if service is RPaaS by looking at openapi-subtype in resource-manager/readme.md."""
    rm_readme_path = os.path.join(org_path, 'resource-manager', 'readme.md')
    if not os.path.exists(rm_readme_path):
        rm_readme_path = os.path.join(org_path, 'resource-manager', 'README.md')
    
    if not os.path.exists(rm_readme_path):
        return False
    
    try:
        with open(rm_readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Look for openapi-subtype: rpaas
            if 'openapi-subtype:' in content and 'rpaas' in content.lower():
                return True
    except Exception as e:
        print(f"Error reading {rm_readme_path}: {e}")
    
    return False

def check_version_uniform_issues(org_path):
    """Check if organization has version uniform issues in readme.md files."""
    rm_path = os.path.join(org_path, 'resource-manager')
    if not os.path.exists(rm_path):
        return False, []
    
    has_version_uniform_issue = False
    problematic_readmes = []
    
    # Find all readme.md files in resource-manager and nested folders
    readme_files = []
    for root, dirs, files in os.walk(rm_path):
        for file in files:
            if file.lower() in ['readme.md', 'README.md']:
                readme_files.append(os.path.join(root, file))
    
    for readme_path in readme_files:
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find the default tag in Basic Information section
            default_tag = None
            basic_info_match = re.search(r'(## Basic Information.*?)(?=##|\Z)', content, re.DOTALL | re.IGNORECASE)
            if basic_info_match:
                basic_info_section = basic_info_match.group(1)
                # Look for default-tag pattern or tag pattern
                default_tag_match = re.search(r'default-tag:\s*(\S+)', basic_info_section)
                if default_tag_match:
                    default_tag = default_tag_match.group(1)
                else:
                    # Also look for tag: pattern (alternative format)
                    tag_match = re.search(r'tag:\s*(\S+)', basic_info_section)
                    if tag_match:
                        default_tag = tag_match.group(1)
            
            if not default_tag:
                continue
            
            # Find the YAML block for the default tag
            tag_pattern = rf'```\s*yaml.*?\$\(tag\)\s*==\s*[\'"]{re.escape(default_tag)}[\'\"](.*?)```'
            tag_match = re.search(tag_pattern, content, re.DOTALL)
            if not tag_match:
                # Try alternative pattern
                tag_pattern = rf'```\s*yaml\s*\$\({re.escape(default_tag)}\)(.*?)```'
                tag_match = re.search(tag_pattern, content, re.DOTALL)
            
            if not tag_match:
                continue
            
            yaml_block = tag_match.group(1)
            
            # Parse the YAML to find input-file entries
            try:
                yaml_data = yaml.safe_load(yaml_block)
                if not yaml_data or not isinstance(yaml_data, dict):
                    continue
                
                input_files = yaml_data.get('input-file', [])
                if isinstance(input_files, str):
                    input_files = [input_files]
                
                # Extract API versions from input files
                api_versions = set()
                for input_file in input_files:
                    # Extract folder name that represents the API version
                    # Look for patterns like stable/2023-01-01/ or preview/2023-01-01-preview/
                    version_match = re.search(r'/(stable|preview)/([^/]+)/', input_file)
                    if version_match:
                        api_version = version_match.group(2)
                        api_versions.add(api_version)
                
                # Check if there are multiple unique API versions
                if len(api_versions) > 1:
                    has_version_uniform_issue = True
                    rel_readme_path = os.path.relpath(readme_path, org_path)
                    problematic_readmes.append(rel_readme_path)
                    
            except yaml.YAMLError:
                # Skip files with invalid YAML
                continue
                
        except Exception as e:
            # Skip files that can't be read
            continue
    
    return has_version_uniform_issue, problematic_readmes

def analyze_organization(org_path, spec_base_path):
    """Analyze a single organization folder."""
    org_name = os.path.basename(org_path)
    
    # Find TypeSpec projects
    typespec_projects = []
    for root, dirs, files in os.walk(org_path):
        # Skip examples directories
        dirs[:] = [d for d in dirs if d.lower() != 'examples']
        
        if 'tspconfig.yaml' in files or 'main.tsp' in files:
            typespec_projects.append(root)
    
    # Find Swagger files
    swagger_files = find_swagger_files(org_path)
    mgmt_swagger_files, data_swagger_files = classify_swagger_files(swagger_files, org_path)
    
    # Analyze each TypeSpec project
    mgmt_typespec_projects = []
    data_typespec_projects = []
    
    for project in typespec_projects:
        if is_management_plane(project):
            mgmt_typespec_projects.append(project)
        else:
            data_typespec_projects.append(project)
    
    # Check folder structure compliance for relevant folders only:
    # 1. TypeSpec project root folders (containing tspconfig.yaml or main.tsp)
    # 2. Swagger stable/preview folders
    all_folders = []
    compliant_folders = []
    non_compliant_folders = []
    
    # Add TypeSpec project root folders
    for project in typespec_projects:
        all_folders.append(project)
    
    # Find Swagger stable/preview folders
    for root, dirs, files in os.walk(org_path):
        # Skip examples directories
        dirs[:] = [d for d in dirs if d.lower() != 'examples']
        
        # Check if this directory is a stable or preview folder
        folder_name = os.path.basename(root)
        if folder_name.lower() in ['stable', 'preview']:
            # Check if it contains swagger files or has swagger files in subdirectories
            has_swagger_in_this_branch = False
            for subroot, subdirs, subfiles in os.walk(root):
                # Skip examples directories
                subdirs[:] = [d for d in subdirs if d.lower() != 'examples']
                
                for file in subfiles:
                    if file.endswith('.json'):
                        file_path = os.path.join(subroot, file)
                        if 'examples' not in file_path.lower():
                            has_swagger_in_this_branch = True
                            break
                if has_swagger_in_this_branch:
                    break
            
            if has_swagger_in_this_branch:
                all_folders.append(root)
    
    # Check compliance for each folder
    for folder in all_folders:
        is_compliant, reason = check_folder_structure_v2_compliance(folder, spec_base_path)
        if is_compliant:
            compliant_folders.append(folder)
        else:
            non_compliant_folders.append((folder, reason))
    
    # Check other attributes
    has_dp_swagger = has_data_plane_swagger(org_path)
    readme_count = count_readme_files_in_resource_manager(org_path)
    is_rpaas = is_rpaas_service(org_path)
    has_version_uniform_issue, problematic_readmes = check_version_uniform_issues(org_path)
    
    # Determine if the entire organization is compliant (all folders are compliant)
    org_is_fully_compliant = len(non_compliant_folders) == 0 and len(all_folders) > 0
    
    # Check if structure is simple
    is_simple_structure = True
    
    # Check management plane structure simplicity
    if len(mgmt_typespec_projects) > 0:
        # Find all resource-manager stable/preview folders
        mgmt_stable_preview_parents = set()
        for root, dirs, files in os.walk(org_path):
            # Skip examples directories
            dirs[:] = [d for d in dirs if d.lower() != 'examples']
            
            folder_name = os.path.basename(root)
            if folder_name.lower() in ['stable', 'preview'] and 'resource-manager' in root:
                # Check if it contains swagger files
                has_swagger_in_this_branch = False
                for subroot, subdirs, subfiles in os.walk(root):
                    subdirs[:] = [d for d in subdirs if d.lower() != 'examples']
                    for file in subfiles:
                        if file.endswith('.json'):
                            file_path = os.path.join(subroot, file)
                            if 'examples' not in file_path.lower():
                                has_swagger_in_this_branch = True
                                break
                    if has_swagger_in_this_branch:
                        break
                
                if has_swagger_in_this_branch:
                    # Get the direct parent folder of stable/preview
                    parent_folder = os.path.dirname(root)
                    mgmt_stable_preview_parents.add(parent_folder)
        
        # Check if number of unique parent folders equals number of mgmt TypeSpec projects
        if len(mgmt_stable_preview_parents) != len(mgmt_typespec_projects):
            is_simple_structure = False
    
    # Check data plane structure simplicity
    if len(data_typespec_projects) > 0:
        # Find all data-plane stable/preview folders
        data_stable_preview_parents = set()
        for root, dirs, files in os.walk(org_path):
            # Skip examples directories
            dirs[:] = [d for d in dirs if d.lower() != 'examples']
            
            folder_name = os.path.basename(root)
            if folder_name.lower() in ['stable', 'preview'] and 'data-plane' in root:
                # Check if it contains swagger files
                has_swagger_in_this_branch = False
                for subroot, subdirs, subfiles in os.walk(root):
                    subdirs[:] = [d for d in subdirs if d.lower() != 'examples']
                    for file in subfiles:
                        if file.endswith('.json'):
                            file_path = os.path.join(subroot, file)
                            if 'examples' not in file_path.lower():
                                has_swagger_in_this_branch = True
                                break
                    if has_swagger_in_this_branch:
                        break
                
                if has_swagger_in_this_branch:
                    # Get the direct parent folder of stable/preview
                    parent_folder = os.path.dirname(root)
                    data_stable_preview_parents.add(parent_folder)
        
        # Check if number of unique parent folders equals number of data TypeSpec projects
        if len(data_stable_preview_parents) != len(data_typespec_projects):
            is_simple_structure = False
    
    return {
        'organization': org_name,
        'total_typespec_projects': len(typespec_projects),
        'management_plane_typespec_projects': len(mgmt_typespec_projects),
        'data_plane_typespec_projects': len(data_typespec_projects),
        'total_swagger_files': len(swagger_files),
        'management_plane_swagger_files': len(mgmt_swagger_files),
        'data_plane_swagger_files': len(data_swagger_files),
        'total_folders': len(all_folders),
        'compliant_folders': len(compliant_folders),
        'non_compliant_folders': len(non_compliant_folders),
        'org_fully_compliant': org_is_fully_compliant,
        'is_simple_structure': is_simple_structure,
        'non_compliant_details': non_compliant_folders,
        'has_data_plane_swagger': has_dp_swagger,
        'readme_count_in_rm': readme_count,
        'is_rpaas_service': is_rpaas,
        'has_version_uniform_issue': has_version_uniform_issue,
        'problematic_readmes': problematic_readmes,
        'typespec_project_paths': typespec_projects,
        'mgmt_typespec_project_paths': mgmt_typespec_projects,
        'data_typespec_project_paths': data_typespec_projects,
        'swagger_file_paths': swagger_files,
        'mgmt_swagger_file_paths': mgmt_swagger_files,
        'data_swagger_file_paths': data_swagger_files,
        'all_folder_paths': all_folders,
        'compliant_folder_paths': compliant_folders,
        'non_compliant_folder_paths': [path for path, reason in non_compliant_folders]
    }

def main():
    """Main analysis function."""
    spec_base_path = '/Users/qiaoqiaozhang/code/azure-rest-api-specs/specification'
    
    # Get all organization directories
    org_dirs = []
    for item in os.listdir(spec_base_path):
        item_path = os.path.join(spec_base_path, item)
        if os.path.isdir(item_path) and not item.startswith('.') and item != 'suppressions.yaml':
            org_dirs.append(item_path)
    
    print(f"Found {len(org_dirs)} organization directories to analyze...")
    
    # Analyze each organization
    results = []
    for i, org_path in enumerate(org_dirs, 1):
        org_name = os.path.basename(org_path)
        print(f"Analyzing {i}/{len(org_dirs)}: {org_name}")
        
        try:
            result = analyze_organization(org_path, spec_base_path)
            results.append(result)
        except Exception as e:
            print(f"Error analyzing {org_name}: {e}")
            # Add basic entry for failed analysis
            results.append({
                'organization': org_name,
                'total_typespec_projects': 0,
                'management_plane_typespec_projects': 0,
                'data_plane_typespec_projects': 0,
                'total_swagger_files': 0,
                'management_plane_swagger_files': 0,
                'data_plane_swagger_files': 0,
                'total_folders': 0,
                'compliant_folders': 0,
                'non_compliant_folders': 0,
                'org_fully_compliant': False,
                'is_simple_structure': True,  # Default for failed analysis
                'non_compliant_details': [],
                'has_data_plane_swagger': False,
                'readme_count_in_rm': 0,
                'is_rpaas_service': False,
                'has_version_uniform_issue': False,
                'problematic_readmes': [],
                'typespec_project_paths': [],
                'mgmt_typespec_project_paths': [],
                'data_typespec_project_paths': [],
                'swagger_file_paths': [],
                'mgmt_swagger_file_paths': [],
                'data_swagger_file_paths': [],
                'all_folder_paths': [],
                'compliant_folder_paths': [],
                'non_compliant_folder_paths': [],
                'error': str(e)
            })
    
    # Create summary statistics
    total_typespec = sum(r['total_typespec_projects'] for r in results)
    total_mgmt_typespec = sum(r['management_plane_typespec_projects'] for r in results)
    total_data_typespec = sum(r['data_plane_typespec_projects'] for r in results)
    total_swagger = sum(r['total_swagger_files'] for r in results)
    total_mgmt_swagger = sum(r['management_plane_swagger_files'] for r in results)
    total_data_swagger = sum(r['data_plane_swagger_files'] for r in results)
    total_folders = sum(r['total_folders'] for r in results)
    total_compliant_folders = sum(r['compliant_folders'] for r in results)
    total_non_compliant_folders = sum(r['non_compliant_folders'] for r in results)
    total_fully_compliant_orgs = sum(1 for r in results if r['org_fully_compliant'])
    
    print(f"\n=== SUMMARY ===")
    print(f"Total organizations analyzed: {len(results)}")
    print(f"Fully compliant organizations: {total_fully_compliant_orgs}")
    print(f"Total TypeSpec projects: {total_typespec}")
    print(f"  - Management plane TypeSpec: {total_mgmt_typespec}")
    print(f"  - Data plane TypeSpec: {total_data_typespec}")
    print(f"Total Swagger files: {total_swagger}")
    print(f"  - Management plane Swagger: {total_mgmt_swagger}")
    print(f"  - Data plane Swagger: {total_data_swagger}")
    print(f"Total folders analyzed: {total_folders}")
    print(f"Folder structure v2 compliant folders: {total_compliant_folders}")
    print(f"Folder structure v2 non-compliant folders: {total_non_compliant_folders}")
    
    # Convert to DataFrame and save to Excel - Simplified Report
    df_data = []
    for result in results:
        # Check if has data plane (both TypeSpec and Swagger)
        has_data_plane_typespec = result['data_plane_typespec_projects'] > 0
        has_data_plane_swagger = result['has_data_plane_swagger']
        has_data_plane = has_data_plane_typespec or has_data_plane_swagger
        
        # Check if has TypeSpec in management plane or data plane
        has_mgmt_plane_typespec = result['management_plane_typespec_projects'] > 0
        has_mgmt_or_data_plane_typespec = has_mgmt_plane_typespec or has_data_plane_typespec
        
        # Get compliant and non-compliant folder paths
        compliant_folder_paths = [os.path.relpath(p, spec_base_path) for p in result['compliant_folder_paths']]
        non_compliant_folder_paths = [os.path.relpath(p, spec_base_path) for p in result['non_compliant_folder_paths']]
        problematic_readmes_str = ';'.join(result['problematic_readmes']) if result['problematic_readmes'] else ''
        
        df_data.append({
            'Organization': result['organization'],
            'Fully Compliant': result['org_fully_compliant'],
            'Is Simple Structure': result['is_simple_structure'],
            'Is RPaaS Service': result['is_rpaas_service'],
            'Has Data Plane': has_data_plane,
            'Has TypeSpec': has_mgmt_or_data_plane_typespec,
            'Has Version Uniform Issue': result['has_version_uniform_issue'],
            'Problematic Readmes': problematic_readmes_str,
            'Compliant Folders': ';'.join(compliant_folder_paths),
            'Non-Compliant Folders': ';'.join(non_compliant_folder_paths)
        })
    
    df = pd.DataFrame(df_data)
    
    # Save to Excel - Simplified Report
    output_file = '/Users/qiaoqiaozhang/code/azure-rest-api-specs/specification_analysis_simplified_report.xlsx'
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Main simplified analysis
        df.to_excel(writer, sheet_name='Simplified Analysis Report', index=False)
        
        # Summary statistics
        total_orgs = len(results)
        fully_compliant_orgs = len([r for r in results if r['org_fully_compliant']])
        rpaas_orgs = len([r for r in results if r['is_rpaas_service']])
        has_data_plane_orgs = len([r for r in results if r['data_plane_typespec_projects'] > 0 or r['has_data_plane_swagger']])
        has_both_planes_typespec_orgs = len([r for r in results if r['management_plane_typespec_projects'] > 0 or r['data_plane_typespec_projects'] > 0])
        
        summary_data = [
            ['Total Organizations', total_orgs],
            ['Fully Compliant Organizations', fully_compliant_orgs],
            ['RPaaS Organizations', rpaas_orgs],
            ['Organizations with Data Plane (TypeSpec or Swagger)', has_data_plane_orgs],
            ['Organizations with TypeSpec Projects', len([r for r in results if r['total_typespec_projects'] > 0])],
            ['Organizations with Swagger Files', len([r for r in results if r['total_swagger_files'] > 0])],
            ['Organizations with TypeSpec (Mgmt or Data Plane)', has_both_planes_typespec_orgs]
        ]
        summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Count'])
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"\nSimplified analysis complete! Report saved to: {output_file}")
    
    return df

if __name__ == "__main__":
    main()
