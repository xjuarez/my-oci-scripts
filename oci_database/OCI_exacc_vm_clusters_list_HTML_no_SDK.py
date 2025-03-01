#!/usr/bin/env python3

# --------------------------------------------------------------------------------------------------------------
# This script lists all ExaCC VM clusters and Exadata Infrastructures in a OCI tenant using OCI Python SDK 
# It looks in all compartments in the region given by profile or in all subscribed regions
# Note: OCI tenant given by an OCI CLI PROFILE or by instance principal authentication
#
# Authors       : Christophe Pauliat / Matthieu Bordonné
# Platforms     : MacOS / Linux
# prerequisites : - Python 3 with OCI Python SDK installed
#                 - OCI config file configured with profiles (not needed if using instance principal authentication)
# Versions
#    2022-07-29: Create a version of an existing Python/OCI SDK script that does not use Python SDK (uses raw REST APIs request)
#
# IMPORTANT: it is recommended to use the Python SDK version of this script instead of this version
# --------------------------------------------------------------------------------------------------------------

# -------- import
from re import T
import sys
import argparse
import os
import smtplib
import email.utils
import operator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from pkg_resources import parse_version
# from oci.config import from_file
from oci.signer import Signer
import requests
import json

# -------- variables
days_notification      = 15                 # Number of days before scheduled maintenance
color_date_soon        = "#FF0000"          # Color for maintenance scheduled soon (less than days_notification days)
color_not_available    = "#FF0000"          # Color for lifecycles different than AVAILABLE and ACTIVE
color_pdb_read_write   = "#009900"
color_pdb_read_only    = "#FF9900"
color_pdb_others       = "#FF0000"
configfile             = "/Users/cpauliat/.oci/config"  # "~/.oci/config"    # Define config file to be used.
exadatainfrastructures = []
vmclusters             = []
autonomousvmclusters   = []
db_homes               = []
auto_cdbs              = []
auto_dbs               = []

# -------- functions

# ---- replacement for oci.config.from_file() function in OCI SDK
def from_file2(oci_config_file, oci_profile):
    # read the OCI config file and look for the OCI profile 
    with open(oci_config_file) as f:
        lines = [line.rstrip() for line in f]
    c1 = 0
    for line in lines:
        if line == f"[{oci_profile}]":
            break
        c1 += 1

    # profile not found
    if line != f"[{oci_profile}]":
        raise ValueError(f"OCI profile {oci_profile} not found !")

    # get the first line (c1) and last line (c2) of the profile
    c1 +=1
    c2 = c1
    while lines[c2] != "" and c2 < len(lines)-1:
        c2 += 1

    # create a dictionary containing the key/value pairs of the profile
    my_config = {}
    my_config['tenancy']     = ''
    my_config['user']        = ''
    my_config['fingerprint'] = ''
    my_config['key_file']    = ''
    my_config['region']      = ''
    my_config['pass_phrase'] = ''

    for line in lines[c1:c2]:
        kv = line.split('=')
        my_config[kv[0].strip()] = kv[1].strip()

    print (f"FOUND profile: my_config={my_config}",file=sys.stderr)
    return my_config

def response_warning(response, function_name):
    try:
        response.raise_for_status()
    except Exception as err:
        print (f"WARNING in {function_name}: {err}",file=sys.stderr)

def response_error(response, function_name):
    try:
        response.raise_for_status()
    except Exception as err:
        print (f"ERROR in {function_name}: {err}",file=sys.stderr)
        exit (1)

def print_json(text):
    print (json.dumps(text, sort_keys=True, indent=4), file=sys.stderr)

def set_region_and_endpoints(region_name):
    global endpoints
    global current_region 
    
    current_region = region_name
    endpoints = {}
    endpoints['iam']           = f"https://identity.{region_name}.oci.oraclecloud.com"
    endpoints['core']          = f"https://iaas.{region_name}.oraclecloud.com"
    endpoints['search']        = f"https://query.{region_name}.oraclecloud.com"
    endpoints['database']      = f"https://database.{region_name}.oraclecloud.com"
    endpoints['objectstorage'] = f"https://objectstorage.{region_name}.oraclecloud.com"

def get_subscribed_regions():
    api_url = f"{endpoints['iam']}/20160918/tenancies/{oci_tenancy_id}/regionSubscriptions"

    my_params = { 
        "tenancyId": oci_tenancy_id
    }

    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "get_subscribed_regions()")
    regions = response.json()

    return regions

def get_all_compartments():
    api_url = f"{endpoints['iam']}/20160918/compartments"

    my_params = { 
        "compartmentId": oci_tenancy_id,
        "compartmentIdInSubtree": True
    }

    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "get_all_compartments()")
    compartments = response.json()
    while 'opc-next-page' in response.headers:    
        my_params = { 
            "compartmentId": oci_tenancy_id,
            "compartmentIdInSubtree": True,
            "page": response.headers['opc-next-page']
        }  
        response = requests.get(api_url, params=my_params, auth=auth)
        response_error(response, "get_all_compartments()")
        compartments += response.json()

    return compartments

def get_tenant_name():
    api_url = f"{endpoints['iam']}/20160918/tenancies/{oci_tenancy_id}"

    my_params = { 
        "tenancyId": oci_tenancy_id
    }

    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "get_tenant_name()")
    tenancy = response.json()

    return tenancy['name']

# ---- Search OCI ressources
def search_resources(query):
    api_url = f"{endpoints['search']}/20180409/resources"

    my_params = { 
        "limit": 1000
    }
    body = {
        "type": "Structured",
        "query": query
    }
    response = requests.post(api_url, params=my_params, json=body, auth=auth)
    response_error(response, "search_resources()")
    return response.json()['items']

# ---- Get list of Exadata infrastructures
def search_exadatainfrastructures():
    items = search_resources("query exadatainfrastructure resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        exadatainfrastructure_get_details(item['identifier'])

def exadatainfrastructure_get_details(exadatainfrastructure_id):
    global exadatainfrastructures

    api_url = f"{endpoints['database']}/20160918/exadataInfrastructures/{exadatainfrastructure_id}"
    my_params = { 
        "exadataInfrastructureId": exadatainfrastructure_id
    }

    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "exadatainfrastructure_get_details()")
    exainfra = response.json()
    exainfra['region'] = current_region

    exainfra['lastMaintenanceStart'], exainfra['lastMaintenanceEnd'] = get_last_maintenance_dates(exainfra['lastMaintenanceRunId'])
    exainfra['nextMaintenance'] = get_next_maintenance_date(exainfra['nextMaintenanceRunId'])

    # save details to list
    exadatainfrastructures.append (exainfra)

# ---- Get list of VM clusters
def search_vmclusters():
    items = search_resources("query vmcluster resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        vmcluster_get_details(item['identifier'])

def vmcluster_get_details(vmcluster_id):
    global vmclusters

    # get VM cluster details
    api_url = f"{endpoints['database']}/20160918/vmClusters/{vmcluster_id}"
    my_params = { 
        "vmClusterId": vmcluster_id
    }

    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "vmcluster_get_details() #1")
    vmcluster = response.json()
    vmcluster['region'] = current_region

    # Get the available GI patches for the VM Cluster
    api_url = f"{endpoints['database']}/20160918/vmClusters/{vmcluster_id}/patches"
    my_params = { 
        "vmClusterId": vmcluster_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "vmcluster_get_details() #2")
    vmclust_gi_updates = response.json()
    vmcluster['giUpdateAvailable'] = vmcluster['giVersion']
    for gi_updates in vmclust_gi_updates:
        if parse_version(gi_updates['version']) > parse_version(vmcluster['giUpdateAvailable']):
            vmcluster['giUpdateAvailable'] = gi_updates['version']

    # Get the available System updates for the VM Cluster
    api_url = f"{endpoints['database']}/20160918/vmClusters/{vmcluster_id}/updates"
    my_params = { 
        "vmClusterId": vmcluster_id,
        "updateType": "OS_UPDATE"
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "vmcluster_get_details() #3")
    vmclust_sys_updates = response.json()
    vmcluster['systemUpdateAvailable'] = vmcluster['systemVersion']
    for sys_updates in vmclust_sys_updates:
        if parse_version(sys_updates['version']) > parse_version(vmcluster['systemUpdateAvailable']):
            vmcluster['systemUpdateAvailable'] = sys_updates['version']

    # save details to list
    vmclusters.append (vmcluster)

# ---- Get the list of DB homes (for VM clusters)
def search_db_homes():
    items = search_resources("query dbhome resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        db_home_get_details(item['identifier'])

def list_databases_in_dbhome(cpt_id, db_home_id):
    api_url = f"{endpoints['database']}/20160918/databases/"
    my_params = { 
        "compartmentId": cpt_id,
        "dbHomeId": db_home_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "list_databases_in_dbhome()")
    return response.json()

def list_pdbs_in_database(database_id):
    api_url = f"{endpoints['database']}/20160918/pluggableDatabases/"
    my_params = { 
        "databaseId": database_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    # No need to test reponse with response_error() or response_warning() here
    # as we have a try/except in the calling function.
    return response.json()

def list_db_home_patches(db_home_id):
    api_url = f"{endpoints['database']}/20160918/dbHomes/{db_home_id}/patches"
    my_params = { 
        "dbHomeId": db_home_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "list_db_home_patches()")
    return response.json()

def db_home_get_details(db_home_id):
    global db_homes

    # Get DB home details
    api_url = f"{endpoints['database']}/20160918/dbHomes/{db_home_id}"
    my_params = { 
        "dbHomeId": db_home_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "db_home_get_details()")
    db_home = response.json()
    db_home['region'] = current_region

    # Get the latest patch available (DB version) for the DB HOME
    db_home_updates = list_db_home_patches(db_home_id)
    db_home['dbUpdateLatest'] = db_home['dbVersion']
    for update in db_home_updates:
        if parse_version(update['version']) > parse_version(db_home['dbUpdateLatest']):
            db_home['dbUpdateLatest'] = update['version']

    # Get the list of databases (and pluggable databases) using this DB home
    db_home['databases'] = list_databases_in_dbhome(db_home['compartmentId'], db_home_id)
    for database in db_home['databases']:
        # OCI pluggable database management is supported only for Oracle Database 19.0 or higher
        try:
            if database['isCdb']:
                database['pdbs'] = list_pdbs_in_database(database['id'])
        except:
            pass

    # save details to list
    db_homes.append (db_home)

# ---- Get list of Autonomous VM clusters
def search_autonomousvmclusters():
    items = search_resources("query autonomousvmcluster resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        if item['lifecycleState'] != "TERMINATED":
            autonomousvmcluster_get_details(item['identifier'])

def autonomousvmcluster_get_details(autonomousvmcluster_id):
    global autonomousvmclusters

    api_url = f"{endpoints['database']}/20160918/autonomousVmClusters/{autonomousvmcluster_id}"
    my_params = { 
        "autonomousVmClusterId": autonomousvmcluster_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "autonomousvmcluster_get_details()")
    autovmclust = response.json()
    autovmclust['region'] = current_region

    # last_maintenance_run_id is currently not populated, hence the workaround below 
    # Get a list of historical maintenance runs for that AVM Cluster and find the latest
    last_maintenance_run_id = get_last_maintenance_run_id(autovmclust['compartmentId'], autovmclust['id'])
    autovmclust['lastMaintenanceStart'], autovmclust['lastMaintenanceEnd'] = get_last_maintenance_dates(last_maintenance_run_id)
    # End of workaround. Once fixed, replace by this call:
    # autovmclust['lastMaintenanceStart'], autovmclust['lastMaintenanceEnd'] = get_last_maintenance_dates(autovmclust['lastMaintenanceRunId'])
    
    autovmclust['nextMaintenance'] = get_next_maintenance_date(autovmclust['nextMaintenanceRunId'])

    # save details to list
    autonomousvmclusters.append (autovmclust)

# ---- Get the list of Autonomous Container Databases (for autonomous VM clusters)
def search_auto_cdbs():
    items = search_resources("query autonomouscontainerdatabase resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        auto_cdb_get_details(item['identifier'])

def auto_cdb_get_details(auto_cdb_id):
    global auto_cdbs

    # get details about autonomous cdb from regular API 
    api_url = f"{endpoints['database']}/20160918/autonomousContainerDatabases/{auto_cdb_id}"
    my_params = { 
        "autonomousContainerDatabaseId": auto_cdb_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "auto_cdb_get_details()")
    auto_cdb = response.json()
    auto_cdb['region'] = current_region

    # save details to list
    auto_cdbs.append (auto_cdb)

# ---- Get the list of Autonomous Databases (for autonomous VM clusters)
def search_auto_dbs():
    items = search_resources("query autonomousdatabase resources")
    sorted_items = sorted(items, key=operator.itemgetter('displayName'))
    for item in sorted_items:
        auto_db_get_details(item['identifier'])

# ---- Get details for an autonomous database
def auto_db_get_details(auto_db_id):
    global auto_dbs

    # get details about autonomous database from regular API 
    api_url = f"{endpoints['database']}/20160918/autonomousDatabases/{auto_db_id}"
    my_params = { 
        "autonomousDatabaseId": auto_db_id
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_error(response, "auto_db_get_details()")
    auto_db = response.json()
    auto_db['region'] = current_region

    # save details to list
    auto_dbs.append (auto_db)

# ---- Get the details for a next maintenance run
def get_next_maintenance_date(maintenance_run_id):
    if maintenance_run_id:
        api_url = f"{endpoints['database']}/20160918/maintenanceRuns/{maintenance_run_id}"
        my_params = { 
            "maintenanceRunId": maintenance_run_id
        }
        response = requests.get(api_url, params=my_params, auth=auth)
        response_warning(response, "get_next_maintenance_date()")
        return response.json()['timeScheduled']
    else:
        return ""

# ---- Get ID of last maintenance run for an autonomous vm cluster
def get_last_maintenance_run_id(cpt_id, autovmcluster_id):
    api_url = f"{endpoints['database']}/20160918/maintenanceRuns/"
    my_params = { 
        "compartmentId": cpt_id,
        "targetResourceId": autovmcluster_id,
        "sortBy": "TIME_ENDED",
        "sortOrder": "ASC"
    }
    response = requests.get(api_url, params=my_params, auth=auth)
    response_warning(response, "get_last_maintenance_run_id()")
    if len(response.json()) > 0:
        last_maintenance_run_id = response.json()[-1]['id']
    else:
        last_maintenance_run_id = ""

    return last_maintenance_run_id

# ---- Get the details for a last maintenance run
def get_last_maintenance_dates(maintenance_run_id):
    if maintenance_run_id:
        api_url = f"{endpoints['database']}/20160918/maintenanceRuns/{maintenance_run_id}"
        my_params = { 
            "maintenanceRunId": maintenance_run_id
        }
        response = requests.get(api_url, params=my_params, auth=auth)
        response_warning(response, "get_last_maintenance_dates()")
        date_started = response.json()['timeStarted']
        date_ended   = response.json()['timeEnded']
    else:
        date_started = ""
        date_ended   = ""
    
    return date_started, date_ended

# ---- Get the complete name of a compartment from its id, including parent and grand-parent..
def get_cpt_name_from_id(cpt_id,level=0):

    if cpt_id == RootCompartmentID:
        return "root"

    name = ""
    for c in compartments:
        if (c['id'] == cpt_id):
            name = c['name']

            # if the cpt is a direct child of root compartment, return name
            if c['compartmentId'] == RootCompartmentID:
                return name
            # otherwise, find name of parent and add it as a prefix to name
            else:
                name = get_cpt_name_from_id(c['compartmentId'],level+1)+":"+name
                return name

# ---- Get url link to a specific Exadata infrastructure in OCI Console
def get_url_link_for_exadatainfrastructure(exadatainfrastructure):
    return f"https://cloud.oracle.com/exacc/infrastructures/{exadatainfrastructure['id']}?tenant={tenant_name}&region={exadatainfrastructure['region']}"

# ---- Get url link to a specific VM cluster in OCI Console
def get_url_link_for_vmcluster(vmcluster):
    return f"https://cloud.oracle.com/exacc/clusters/{vmcluster['id']}?tenant={tenant_name}&region={vmcluster['region']}"

# ---- Get url link to a specific autonomous VM cluster in OCI Console
def get_url_link_for_autonomousvmcluster(vmcluster):
    return f"https://cloud.oracle.com/exacc/autonomousExaVmClusters/{vmcluster['id']}?tenant={tenant_name}&region={vmcluster['region']}"

# ---- Get url link to a specific DB home in OCI Console
def get_url_link_for_db_home(db_home):
    return f"https://cloud.oracle.com/exacc/db_homes/{db_home['id']}?tenant={tenant_name}&region={db_home['region']}"

# ---- Get url link to a specific database in OCI Console
def get_url_link_for_database(database, region):
    return f"https://cloud.oracle.com/exacc/databases/{database['id']}?tenant={tenant_name}&region={region}"

# ---- Get url link to a specific pdb in OCI Console
def get_url_link_for_pdb(pdb, region):
    return f"https://cloud.oracle.com/exacc/pluggableDatabases/{pdb['id']}?tenant={tenant_name}&region={region}"

# ---- Get url link to a specific autonomous container database in OCI Console
def get_url_link_for_auto_cdb(auto_cdb):
    return f"https://cloud.oracle.com/exacc/autonomousContainerDatabases/{auto_cdb['id']}?tenant={tenant_name}&region={auto_cdb['region']}"

# ---- Get url link to a specific autonomous  database in OCI Console
def get_url_link_for_auto_db(auto_db):
    return f"https://cloud.oracle.com/exacc/autonomousDatabases/{auto_db['id']}?tenant={tenant_name}&region={auto_db['region']}"

# ---- Generate HTML page 
def generate_html_headers():
    html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <title>ExaCC status report</title>
    <style type="text/css">
        tr:nth-child(odd) {{ background-color: #f2f2f2; }}
        tr:hover          {{ background-color: #ffdddd; }}
        body {{
            font-family: Arial;
        }}
        table {{
            border-collapse: collapse;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
        tr {{
            background-color: #FFF5F0;
        }}
        th, td {{
            border: 1px solid #808080;
            text-align: center;
            padding: 7px;
        }}
        .auto_td_th {{
            font-size: 0.85vw;
        }}
        .auto_h1 {{
            font-size: 2vw;
        }}
        .auto_h2 {{
            font-size: 1.5vw;
        }}
        .auto_h3 {{
            font-size: 1.1vw;
        }}
        .auto_text_outside_tables {{
            font-size: 0.95vw;
        }}
        caption {{
            caption-side: bottom;
            padding: 10px;
            font-style: italic;
        }}
        // a.pdb:link {{
        //     font-size: 0.75vw;
        // }}
        a.pdb_link_read_write:link {{
            color: {color_pdb_read_write};
        }}
        a.pdb_link_read_write:visited {{
            color: {color_pdb_read_write};
        }}
        a.pdb_link_read_only:link {{
            color: {color_pdb_read_only};
        }}
        a.pdb_link_read_write:visited {{
            color: {color_pdb_read_only};
        }}
        a.pdb_link_others:link {{
            color: {color_pdb_others};
        }}
        a.pdb_link_others:visited {{
            color: {color_pdb_others};
        }}'''

    html_content += '''
    </style>'''

    return html_content

def generate_html_table_exadatainfrastructures():
    html_content  = '''
    <div id="div_exainfras">
        <h2>ExaCC Exadata infrastructures</h2>'''

    # if there is no exainfra, just display None
    if len(exadatainfrastructures) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 exainfra, so display a table
    html_content += '''
        <table id="table_exainfras">
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>EXADATA<br>INFRASTRUCTURE</th>
                    <th>Compartment</th>
                    <th class="exacc_maintenance">Quarterly<br>maintenances</th>
                    <th>Shape</th>
                    <th>Compute Nodes<br>/ Storage Nodes</th>
                    <th>OCPUs<br>/ total</th>
                    <th>Status</th>
                    <th>VM cluster(s)</th>
                    <th>Autonomous<br>VM cluster(s)</th>
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        format     = "%b %d %Y %H:%M %Z"
        cpt_name   = get_cpt_name_from_id(exadatainfrastructure['compartmentId'])
        url        = get_url_link_for_exadatainfrastructure(exadatainfrastructure)
        html_style = f' style="color: {color_not_available}"' if (exadatainfrastructure['lifecycleState'] != "ACTIVE") else ''

        html_content += f'''
                <tr>
                    <td>&nbsp;{exadatainfrastructure['region']}&nbsp;</td>
                    <td>&nbsp;<b><a href="{url}">{exadatainfrastructure['displayName']}</a></b> &nbsp;</td>
                    <td>&nbsp;{cpt_name}&nbsp;</td>
                    <td class="exacc_maintenance" style="text-align: left">&nbsp;Last maintenance: <br>'''

        try:
            last_maintenance_start = datetime.strptime(exadatainfrastructure['lastMaintenanceStart'], '%Y-%m-%dT%H:%M:%S.%f%z')
            html_content += f'''
                        &nbsp; - {last_maintenance_start.strftime(format)} (start)&nbsp;<br>'''
        except:
            html_content += f'''
                        &nbsp; - no date/time (start)&nbsp;<br>'''

        try:
            last_maintenance_end   = datetime.strptime(exadatainfrastructure['lastMaintenanceEnd'], '%Y-%m-%dT%H:%M:%S.%f%z')
            html_content += f'''
                        &nbsp; - {last_maintenance_end.strftime(format)} (end)&nbsp;<br><br>'''
        except:
            html_content += f'''
                        &nbsp; - no date/time (end)&nbsp;<br><br>'''
        
        html_content += f'''
                        &nbsp;Next maintenance: <br>'''

        if exadatainfrastructure['nextMaintenance'] == "":
            html_content += f'''
                        &nbsp; - Not yet scheduled &nbsp;</td>'''
        else:
            # if the next maintenance date is soon, highlight it using a different color
            next_maintenance = datetime.strptime(exadatainfrastructure['nextMaintenance'], '%Y-%m-%dT%H:%M:%S.%f%z')
            if (next_maintenance - now < timedelta(days=days_notification)):
                html_content += f'''
                        &nbsp; - <span style="color: {color_date_soon}">{next_maintenance.strftime(format)}</span>&nbsp;</td>'''
            else:
                html_content += f'''
                        &nbsp; - {next_maintenance.strftime(format)}&nbsp;</td>'''

        html_content += f'''
                    <td>&nbsp;{exadatainfrastructure['shape']}&nbsp;</td>
                    <td>&nbsp;{exadatainfrastructure['computeCount']} / {exadatainfrastructure['storageCount']}&nbsp;</td>
                    <td>&nbsp;{exadatainfrastructure['cpusEnabled']} / {exadatainfrastructure['maxCpuCount']}&nbsp;</td>
                    <td>&nbsp;<span{html_style}>{exadatainfrastructure['lifecycleState']}&nbsp;</span></td>'''

        vmc = []
        for vmcluster in vmclusters:
            if vmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                url = get_url_link_for_vmcluster(vmcluster)
                vmc.append(f'<a href="{url}">{vmcluster["displayName"]}</a>')
        separator = '&nbsp;<br>&nbsp;'
        html_content += f'''
                    <td>&nbsp;{separator.join(vmc)}&nbsp;</td>'''

        avmc = []
        for autonomousvmcluster in autonomousvmclusters:
            if autonomousvmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                url = get_url_link_for_autonomousvmcluster(autonomousvmcluster)
                avmc.append(f'<a href="{url}">{autonomousvmcluster["displayName"]}</a>')
        separator = '&nbsp;<br>&nbsp;'
        html_content += f'''
                    <td>&nbsp;{separator.join(avmc)}&nbsp;</td>
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_table_vmclusters():
    html_content  = '''
    <div id="div_vmclusters">
        <br>
        <h2>ExaCC VM Clusters</h2>'''

    # if there is no vm cluster, just display None
    if len(vmclusters) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 vm cluster, so display a table
    html_content += '''
        <table id="table_vmclusters">
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>Exadata<br>infrastructure</th>
                    <th>VM CLUSTER</th>
                    <th>Compartment</th>
                    <th>Status</th>
                    <th>DB<br>nodes</th>
                    <th>OCPUs</th>
                    <th>Memory<br>(GB)</th>
                    <th>GI Version<br>Current / Latest</th>
                    <th>OS Version<br>Current / Latest</th>'''
    if display_dbs:
        html_content += '''
                    <th class="exacc_databases">DB Home(s) : <i>Databases...</i></th>'''

    html_content += '''
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        for vmcluster in vmclusters:
            if vmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                url        = get_url_link_for_exadatainfrastructure(exadatainfrastructure)      
                cpt_name   = get_cpt_name_from_id(vmcluster['compartmentId'])
                url        = get_url_link_for_vmcluster(vmcluster)
                html_style = f' style="color: {color_not_available}"' if (vmcluster['lifecycleState'] != "AVAILABLE") else ''

                html_content += f'''
                <tr>
                    <td>&nbsp;{vmcluster['region']}&nbsp;</td>\
                    <td>&nbsp;<a href="{url}">{exadatainfrastructure['displayName']}</a>&nbsp;</td>
                    <td>&nbsp;<b><a href="{url}">{vmcluster['displayName']}</a></b> &nbsp;</td>
                    <td>&nbsp;{cpt_name}&nbsp;</td>
                    <td>&nbsp;<span{html_style}>{vmcluster['lifecycleState']}&nbsp;</span></td>
                    <td>&nbsp;{len(vmcluster['dbServers'])}&nbsp;</td>
                    <td>&nbsp;{vmcluster['cpusEnabled']}&nbsp;</td>
                    <td>&nbsp;{vmcluster['memorySizeInGBs']}&nbsp;</td>
                    <td>&nbsp;{vmcluster['giVersion']}&nbsp;/<br>&nbsp;{vmcluster['giUpdateAvailable']}&nbsp;</td>
                    <td>&nbsp;{vmcluster['systemVersion']}&nbsp;/<br>&nbsp;{vmcluster['systemUpdateAvailable']}&nbsp;</td>'''

                if display_dbs:
                    html_content += '''
                    <td class="exacc_databases" style="text-align: left">'''
                    for db_home in db_homes:
                        if db_home['vmClusterId'] == vmcluster['id']:
                            url = get_url_link_for_db_home(db_home)
                            html_content += f'''
                        &nbsp;<a href="{url}">{db_home['displayName']}</a> : '''
                            for database in db_home['databases']:
                                html_content += f'''
                            &nbsp;<i>{database['dbName']}</i>'''
                            html_content += f'''
                            <br>'''
                    html_content += '''
                    </td>'''

                html_content += '''
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_table_db_homes():
    format   = "%b %d %Y %H:%M %Z"
    html_content  = '''
    <div id="div_dbhomes">
        <br>
        <h2>ExaCC Database Homes</h2>'''

    # if there is no db home, just display None
    if len(db_homes) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 vm cluster, so display a table
    html_content += f'''
        <table id="table_dbhomes">
            <caption>Note: Color coding for pluggable databases (PDBs) open mode in last column: 
                <span style="color: {color_pdb_read_write}">READ_WRITE</span>
                <span style="color: {color_pdb_read_only}">READ_ONLY</span>
                <span style="color: {color_pdb_others}">MOUNTED and others</span>
            </caption>
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>Exadata<br>Infrastructure</th>
                    <th>VM cluster</th>
                    <th>DB HOME</th>
                    <th>Status</th>
                    <th>DB version<br>Current / Latest</th>
                    <th>Databases : PDBs</th>
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        for vmcluster in vmclusters:
            if vmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                for db_home in db_homes:
                    if db_home['vmClusterId'] == vmcluster['id']:
                        url1       = get_url_link_for_exadatainfrastructure(exadatainfrastructure)
                        url2       = get_url_link_for_vmcluster(vmcluster)
                        url3       = get_url_link_for_db_home(db_home)
                        html_style = f' style="color: {color_not_available}"' if (db_home['lifecycleState'] != "AVAILABLE") else ''

                        html_content += f'''
                <tr>
                    <td>&nbsp;{db_home['region']}&nbsp;</td>
                    <td>&nbsp;<a href="{url1}">{exadatainfrastructure['displayName']}</a> &nbsp;</td>
                    <td>&nbsp;<a href="{url2}">{vmcluster['displayName']}</a> &nbsp;</td>
                    <td>&nbsp;<b><a href="{url3}">{db_home['displayName']}</a></b> &nbsp;</td>
                    <td>&nbsp;<span{html_style}>{db_home['lifecycleState']}&nbsp;</span></td>
                    <td>&nbsp;{db_home['dbVersion']}&nbsp;/&nbsp;{db_home['dbUpdateLatest']}&nbsp;</td>
                    <td style="text-align: left">'''

                        for database in db_home['databases']:
                            url4          = get_url_link_for_database(database, db_home['region'])
                            html_content += f'''
                        &nbsp;<a href="{url4}">{database['dbName']}</a> : '''
                            # OCI pluggable database management is supported only for Oracle Database 19.0 or higher
                            try:
                                if database['isCdb']:
                                    for pdb in database['pdbs']:
                                        url5 = get_url_link_for_pdb(pdb, db_home['region']) 
                                        pdb_link_class = "pdb_link_others"
                                        if pdb['openMode'] == "READ_WRITE":
                                            pdb_link_class = "pdb_link_read_write"
                                        elif pdb['openMode'] == "READ_ONLY":
                                            pdb_link_class = "pdb_link_read_only"
                                        html_content += f'''
                        <a href="{url5}" class="pdb {pdb_link_class}">{pdb['pdbName']}</a> &nbsp; '''
                            except:
                                pass

                            html_content += f'''
                        <br>'''

                        html_content += f'''
                    </td>
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_table_autonomousvmclusters():
    format   = "%b %d %Y %H:%M %Z"
    html_content  = '''
    <div id="div_autovmclusters">
        <br>
        <h2>ExaCC Autonomous VM Clusters</h2>'''

    # if there is no autonomous vm cluster, just display None
    if len(autonomousvmclusters) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 autonomous vm cluster, so display a table
    html_content += '''
        <table id="table_autovmclusters">
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>Exadata<br>infrastructure</th>
                    <th>AUTONOMOUS<br>VM CLUSTER</th>
                    <th>Compartment</th>
                    <th class="exacc_maintenance">Maintenance runs</th>
                    <th>Status</th>
                    <th>OCPUs</th>'''

    if display_dbs:
        html_content += '''
                    <th class="exacc_databases">Autonomous<br>Container<br>Database(s)</th>'''

    html_content += '''
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        for autonomousvmcluster in autonomousvmclusters:
            if autonomousvmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                cpt_name   = get_cpt_name_from_id(autonomousvmcluster['compartmentId'])
                url1       = get_url_link_for_exadatainfrastructure(exadatainfrastructure)      
                url2       = get_url_link_for_autonomousvmcluster(autonomousvmcluster)
                html_style = f' style="color: {color_not_available}"' if (autonomousvmcluster['lifecycleState'] != "AVAILABLE") else ''

                html_content += f'''
                <tr>
                    <td>&nbsp;{autonomousvmcluster['region']}&nbsp;</td>
                    <td>&nbsp;<a href="{url1}">{exadatainfrastructure['displayName']}</a>&nbsp;</td>
                    <td>&nbsp;<b><a href="{url2}">{autonomousvmcluster['displayName']}</a></b> &nbsp;</td>
                    <td>&nbsp;{cpt_name}&nbsp;</td>
                    <td class="exacc_maintenance" style="text-align: left">&nbsp;Last maintenance: <br>'''

                try:
                    last_maintenance_start = datetime.strptime(autonomousvmcluster['lastMaintenanceStart'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    html_content += f'''
                        &nbsp; - {last_maintenance_start.strftime(format)} (start)&nbsp;<br>'''
                except:
                    html_content += f'''
                        &nbsp; - no date/time (start)&nbsp;<br>'''

                try:
                    last_maintenance_end = datetime.strptime(autonomousvmcluster['lastMaintenanceEnd'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    html_content += f'''
                        &nbsp; - {last_maintenance_end.strftime(format)} (end)&nbsp;<br><br>'''
                except:
                    html_content += f'''
                        &nbsp; - no date/time (end)&nbsp;<br><br>'''
                
                html_content += f'''
                        &nbsp;Next maintenance: <br>'''

                if autonomousvmcluster['nextMaintenance'] == "":
                    html_content += f'''
                        &nbsp; - Not yet scheduled &nbsp;</td>'''
                else:
                    # if the next maintenance date is soon, highlight it using a different color
                    next_maintenance = datetime.strptime(autonomousvmcluster['nextMaintenance'], '%Y-%m-%dT%H:%M:%S.%f%z')
                    if (next_maintenance - now < timedelta(days=days_notification)):
                        html_content += f'''
                        &nbsp; - <span style="color: {color_date_soon}">{next_maintenance.strftime(format)}</span>&nbsp;</td>'''
                    else:
                        html_content += f'''
                        &nbsp; - {next_maintenance.strftime(format)}&nbsp;</td>'''

                html_content += f'''
                    <td>&nbsp;<span{html_style}>{autonomousvmcluster['lifecycleState']}&nbsp;</span></td>
                    <td>&nbsp;{autonomousvmcluster['cpusEnabled']}&nbsp;</td>'''

                if display_dbs:
                    acdbs = []
                    for auto_cdb in auto_cdbs:
                        if auto_cdb['autonomousVmClusterId'] == autonomousvmcluster['id']:
                            url = get_url_link_for_auto_cdb(auto_cdb)
                            acdbs.append(f'<a href="{url}">{auto_cdb["displayName"]}</a>')
                    separator = '&nbsp;<br>&nbsp;'
                    html_content += f'''
                    <td class="exacc_databases">&nbsp;{separator.join(acdbs)}&nbsp;</td>'''

                html_content += '''
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_table_autonomous_cdbs():
    format   = "%b %d %Y %H:%M %Z"
    html_content  = '''
    <div id="div_autocdbs">
        <br>
        <h2>ExaCC Autonomous Container Databases</h2>'''

    # if there is no autonomous container database, just display None
    if len(auto_cdbs) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 autonomous container database, so display a table
    html_content += '''
        <table id="table_autocdbs">
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>Exadata<br>infrastructure</th>
                    <th>Autonomous<br>VM Cluster</th>
                    <th>AUTONOMOUS<br>CONTAINER<br>DATABASE</th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Available<br>OCPUs</th>
                    <th>Total<br>OCPUs</th>
                    <th>Autonomous<br>Data Guard</th>
                    <th>Autonomous<br>Database(s)</th>
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        for autonomousvmcluster in autonomousvmclusters:
            if autonomousvmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                for auto_cdb in auto_cdbs:
                    if auto_cdb['autonomousVmClusterId'] == autonomousvmcluster['id']:
                        url1      = get_url_link_for_exadatainfrastructure(exadatainfrastructure)      
                        url2      = get_url_link_for_autonomousvmcluster(autonomousvmcluster)
                        url3      = get_url_link_for_auto_cdb(auto_cdb)
                        dataguard = "Not enabled" if (auto_cdb['role'] == None) else auto_cdb['role']

                        html_content += f'''
                <tr>
                    <td>&nbsp;{auto_cdb['region']}&nbsp;</td>
                    <td>&nbsp;<a href="{url1}">{exadatainfrastructure['displayName']}</a>&nbsp;</td>
                    <td>&nbsp;<a href="{url2}">{autonomousvmcluster['displayName']}</a> &nbsp;</td>
                    <td>&nbsp;<b><a href="{url3}">{auto_cdb['displayName']}</a></b> &nbsp;</td>
                    <td>&nbsp;{auto_cdb['dbVersion']}&nbsp;</td>
                    <td>&nbsp;{auto_cdb['lifecycleState']}&nbsp;</td>
                    <td>&nbsp;{auto_cdb['availableCpus']}&nbsp;</td>
                    <td>&nbsp;{auto_cdb['totalCpus']}&nbsp;</td>
                    <td>&nbsp;{dataguard}&nbsp;</td>'''

                        adbs = []
                        for auto_db in auto_dbs:
                            if auto_db['autonomousContainerDatabaseId'] == auto_cdb['id']:
                                url4 = get_url_link_for_auto_db(auto_db)
                                adbs.append(f'<a href="{url4}">{auto_db["displayName"]}</a>')
                        separator = '&nbsp;<br>&nbsp;'
                        html_content += f'''
                    <td>&nbsp;{separator.join(adbs)}&nbsp;</td>'''
                
                        html_content += '''
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_table_autonomous_dbs():
    format   = "%b %d %Y %H:%M %Z"
    html_content  = '''
    <div id="div_autodbs">
        <br>
        <h2>ExaCC Autonomous Databases</h2>'''

    # if there is no autonomous database, just display None
    if len(auto_dbs) == 0:
        html_content += '''
        None
    </div>'''
        return html_content

    # there is at least 1 autonomous database, so display a table
    html_content += '''
        <table id="table_autodbs">
            <tbody>
                <tr>
                    <th>Region</th>
                    <th>Exadata<br>infrastructure</th>
                    <th>Autonomous<br>VM Cluster</th>
                    <th>Autonomous<br>Container<br>Database</th>
                    <th>AUTONOMOUS<br>DATABASE</th>
                    <th>Status</th>
                    <th>DB Name</th>
                    <th>OCPUs</th>
                    <th>Storage</th>
                    <th>Workload<br>type</th>
                </tr>'''

    for exadatainfrastructure in exadatainfrastructures:
        for autonomousvmcluster in autonomousvmclusters:
            if autonomousvmcluster['exadataInfrastructureId'] == exadatainfrastructure['id']:
                for auto_cdb in auto_cdbs:
                    if auto_cdb['autonomousVmClusterId'] == autonomousvmcluster['id']:
                        for auto_db in auto_dbs:
                            if auto_db['autonomousContainerDatabaseId'] == auto_cdb['id']:
                                url1       = get_url_link_for_exadatainfrastructure(exadatainfrastructure)      
                                url2       = get_url_link_for_autonomousvmcluster(autonomousvmcluster)
                                url3       = get_url_link_for_auto_cdb(auto_cdb)
                                url4       = get_url_link_for_auto_db(auto_db)
                                html_style = f' style="color: {color_not_available}"' if (auto_db['lifecycleState'] != "AVAILABLE") else ''
                                html_content += f'''
                <tr>
                    <td>&nbsp;{auto_db['region']}&nbsp;</td>
                    <td>&nbsp;<a href="{url1}">{exadatainfrastructure["displayName"]}</a>&nbsp;</td>
                    <td>&nbsp;<a href="{url2}">{autonomousvmcluster["displayName"]}</a> &nbsp;</td>
                    <td>&nbsp;<a href="{url3}">{auto_cdb["displayName"]}</a> &nbsp;</td>
                    <td>&nbsp;<b><a href="{url4}">{auto_db["displayName"]}</a></b> &nbsp;</td>
                    <td>&nbsp;<span{html_style}>{auto_db['lifecycleState']}&nbsp;</span></td>
                    <td>&nbsp;{auto_db['dbName']}&nbsp;</td>
                    <td>&nbsp;{auto_db['ocpuCount']}&nbsp;</td>
                    <td>&nbsp;{auto_db['dataStorageSizeInGBs']} GB &nbsp;</td>
                    <td>&nbsp;{auto_db['dbWorkload']}&nbsp;</td>
                </tr>'''

    html_content += '''
            </tbody>
        </table>
    </div>'''

    return html_content

def generate_html_script_head():
    html_content  = '''
    <script>
        function removeClassFromTags(tags, className) {
            for (tag of tags)
            {
                tag.classList.remove(className);
            }            
        }
        
        function addClassToTags(tags, className) {
            for (tag of tags)
            {
                tag.classList.add(className);
            }            
        }

        function automatic_font_sizes_on_off(input_id) {
            var checkbox_val = document.getElementById(input_id).value;
            var td_th_tags = document.querySelectorAll('td,th');
            var h1_tags = document.querySelectorAll('h1');
            var h2_tags = document.querySelectorAll('h2');
            var h3_tags = document.querySelectorAll('h3');
            var text_tags = document.getElementsByClassName("text_outside_tables");
            if (checkbox_val == "on") {
                // disabling
                removeClassFromTags(td_th_tags, "auto_td_th");
                removeClassFromTags(h1_tags, "auto_h1");
                removeClassFromTags(h2_tags, "auto_h2");
                removeClassFromTags(h3_tags, "auto_h3");
                removeClassFromTags(text_tags, "auto_text_outside_tables");
                document.getElementById(input_id).value = "off";
            } else {
                // enabling
                addClassToTags(td_th_tags, "auto_td_th");
                addClassToTags(h1_tags, "auto_h1");
                addClassToTags(h2_tags, "auto_h2");
                addClassToTags(h3_tags, "auto_h3");
                addClassToTags(text_tags, "auto_text_outside_tables");
                document.getElementById(input_id).value = "on";
            }
        }

        function hide_show_rows_in_column(myclass, display, hide_show) {
            var all_col = document.getElementsByClassName(myclass);
                for(var i=0;i<all_col.length;i++)
                {
                    all_col[i].style.display = display;
                }
                document.getElementById(myclass).value = hide_show;
        }

        function hide_show_div(hide_show, div_id) {
            const mydiv = document.getElementById(div_id);
            if (hide_show == "show") {
                mydiv.style.display = 'block';
            } else {
                mydiv.style.display = 'none';
            }
        }

        function hide_show_column(input_id) {
            var checkbox_val = document.getElementById(input_id).value;
            if(checkbox_val == "hide")
            {
                hide_show_rows_in_column(input_id, "none", "show");
            } else {
                hide_show_rows_in_column(input_id, "table-cell", "hide");
            }
            if (input_id == "exacc_databases") {
                hide_show_div(checkbox_val, "div_dbhomes")
                hide_show_div(checkbox_val, "div_autocdbs")
                hide_show_div(checkbox_val, "div_autodbs")
            }
        }
    </script>'''

    return html_content

def generate_html_script_body():
    html_content  = '''
    <script>
        hide_show_column("exacc_maintenance")'''

    if display_dbs:
        html_content += '''
        hide_show_column("exacc_databases")'''

    html_content += '''
    </script>'''

    return html_content

def generate_html_report_options():
    html_content = '''
    <b>Report options:</b><br>
    <input type="checkbox" value="off" id="automatic_font_sizes" onchange="automatic_font_sizes_on_off(this.id);">Automatic font sizes<br>
    <input type="checkbox" value="show" id="exacc_maintenance" onchange="hide_show_column(this.id);" checked>Display quarterly maintenances information<br>'''

    if display_dbs:
        html_content += f'''
    <input type="checkbox" value="show" id="exacc_databases"   onchange="hide_show_column(this.id);" checked>Display databases (DB Homes, databases, PDBs, Autonomous Container databases and Autonomous Databases)'''

    return html_content

def generate_html_report():

    # headers
    html_report = generate_html_headers()

    # Javascript code in head
    if report_options:
        html_report += generate_html_script_head()

    # head end and body start
    html_report += '''
</head>
<body>'''

    # Title
    html_report += f'''
    <h1>ExaCC status report for OCI tenant <span style="color: #0000FF">{tenant_name.upper()}<span></h1>
    <div class="text_outside_tables">
    <b>Date:</b> {now_str}<br>
    <br>'''

    if report_options:
        html_report += generate_html_report_options()

    html_report += f'''
    </div>'''

    # ExaCC Exadata infrastructures
    html_report += generate_html_table_exadatainfrastructures()

    # ExaCC VM Clusters
    html_report += generate_html_table_vmclusters()

    # ExaCC DB homes
    if display_dbs:
        html_report += generate_html_table_db_homes()
    
    # ExaCC Autonomous VM Clusters
    html_report += generate_html_table_autonomousvmclusters()

    # ExaCC Autonomous Container Databases
    if display_dbs:
        html_report += generate_html_table_autonomous_cdbs()

    # ExaCC Autonomous Databases
    if display_dbs:
        html_report += generate_html_table_autonomous_dbs()

    # Javascript code in body
    if report_options:
        html_report += generate_html_script_body()

    # end of body and html page
    html_report += '''
    <br>
</body>
</html>
'''

    #
    return html_report

# ---- send an email to 1 or more recipients 
def send_email(email_recipients, html_report):

    # The email subject
    email_subject = f"{tenant_name.upper()}: ExaCC status report"

    # Create message container - the correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = email_subject
    msg['From']    = email.utils.formataddr((email_sender_name, email_sender_address))
    msg['To']      = email_recipients

    # The email body for recipients with non-HTML email clients.
    # email_body_text = ( "The quarterly maintenance for Exadata Cloud @ Customer group  just COMPLETED.\n\n" 
    #                     f"The maintenance report is stored as object \n" )

    # The email body for recipients with HTML email clients.
    email_body_html = html_report

    # Record the MIME types: text/plain and html
    # part1 = MIMEText(email_body_text, 'plain')
    part2 = MIMEText(email_body_html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case the HTML message, is best and preferred.
    # msg.attach(part1)
    msg.attach(part2)

    # send the EMAIL
    try:
        email_recipients_list = email_recipients.split(",")
        server = smtplib.SMTP(email_smtp_host, email_smtp_port)
        server.ehlo()
        server.starttls()
        #smtplib docs recommend calling ehlo() before & after starttls()
        server.ehlo()
        server.login(email_smtp_user, email_smtp_password)
        server.sendmail(email_sender_address, email_recipients_list, msg.as_string())
        server.close()
    except Exception as err:
        print (f"ERROR in send_email(): {err}", file=sys.stderr)

# ---- get the email configuration from environment variables:
#      EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SENDER_NAME, EMAIL_SENDER_ADDRESS 
def get_email_configuration():
    global email_smtp_user
    global email_smtp_password
    global email_smtp_host
    global email_smtp_port
    global email_sender_name
    global email_sender_address

    try:
        email_smtp_user      = os.environ['EMAIL_SMTP_USER']
        email_smtp_password  = os.environ['EMAIL_SMTP_PASSWORD']
        email_smtp_host      = os.environ['EMAIL_SMTP_HOST']
        email_smtp_port      = os.environ['EMAIL_SMTP_PORT']
        email_sender_name    = os.environ['EMAIL_SENDER_NAME']
        email_sender_address = os.environ['EMAIL_SENDER_ADDRESS']
    except:
        print ("ERROR: the following environments variables must be set for emails: EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SENDER_NAME, EMAIL_SENDER_ADDRESS !", file=sys.stderr )
        exit (3)

# ---- Store the HTML report in an OCI bucket
def store_report_in_bucket(bucket_name, html_report):
    # set object name
    now_str = now.strftime("%Y-%m-%d_%H:%M")
    if args.bucket_suffix:
        object_name = f"ExaCC_report_{now_str}_{args.bucket_suffix}.html"
    else:
        object_name = f"ExaCC_report_{now_str}.html"

    # Get object storage namespace
    api_url = f"{endpoints['objectstorage']}/n/"
    response = requests.get(api_url, auth=auth)
    response_warning(response, "store_report_in_bucket() #1")
    namespace = response.json()

    # Create a new object in the bucket with MIME type text/html
    api_url = f"{endpoints['objectstorage']}/n/{namespace}/b/{bucket_name}/o/{object_name}"
    my_params = { 
        "namespaceName": namespace,
        "bucketName": bucket_name,
        "objectName": object_name
    }
    my_headers = { 
        "Content-Type": 'text/html'
    }
    response = requests.put(api_url, headers=my_headers, params=my_params, data=html_report, auth=auth)
    response_warning(response, "store_report_in_bucket() #2")

# -------- main

# -- parse arguments
parser = argparse.ArgumentParser(description = "List ExaCC VM clusters in HTML format")
parser.add_argument("-a", "--all_regions", help="Do this for all regions", action="store_true")
parser.add_argument("-e", "--email", help="email the HTML report to a list of comma separated email addresses")
parser.add_argument("-bn", "--bucket-name", help="Store the HTML report in an OCI bucket")
parser.add_argument("-bs", "--bucket-suffix", help="Suffix for object name in the OCI bucket (-bn required)")
parser.add_argument("-db", "--databases", help="Display DB Homes, CDBs, PDBs, Autonomous Container Databases and Autonomous Databases", action="store_true")
parser.add_argument("-ro", "--report-options", help="Add report options for dynamic changes in Web browsers", action="store_true")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-p", "--profile", help="OCI profile for user authentication")
# group.add_argument("-ip", "--inst-principal", help="Use instance principal authentication", action="store_true")  # TODO

# TODO: -bn required for -bs

args = parser.parse_args()

profile        = args.profile
all_regions    = args.all_regions
display_dbs    = args.databases
report_options = args.report_options

# if args.inst_principal:
#     authentication_mode = "instance_principal"
# else:
authentication_mode = "user_profile"

if args.email:
    get_email_configuration()

# -- authentication to OCI
if authentication_mode == "user_profile":
    # authentication using user profile
    try:
        config = from_file2(configfile,profile)
    except:
        print (f"ERROR: profile '{profile}' not found in config file {configfile} !", file=sys.stderr)
        exit (2)
    auth = Signer(
        tenancy=config['tenancy'],
        user=config['user'],
        fingerprint=config['fingerprint'],
        private_key_file_location=config['key_file'],
        pass_phrase=config['pass_phrase']
    )
    oci_tenancy_id = config['tenancy']
    RootCompartmentID = oci_tenancy_id

# -- set the endpoints for API calls
set_region_and_endpoints(config['region'])

# -- get list of subscribed regions
regions = get_subscribed_regions()

# -- Find the home region to build the console URLs later
for r in regions:
    if r['isHomeRegion']:
        home_region = r['regionName']

# -- Get list of compartments with all sub-compartments
compartments = get_all_compartments()

# -- Get Tenancy Name
tenant_name = get_tenant_name()

# -- Get current Date and Time (UTC timezone)
now = datetime.now(timezone.utc)
now_str = now.strftime("%c %Z")

# -- OCI 
# -- Run the search query/queries for ExaCC Exadata infrastructures and save results in exadatainfrastructures list
if not(all_regions):
    search_exadatainfrastructures()
else:
    for region in regions:
        set_region_and_endpoints(region['regionName'])
        search_exadatainfrastructures()

# -- Run the search query/queries for ExaCC VM clusters and save results in vmclusters list
if not(all_regions):
    search_vmclusters()
else:
    for region in regions:
        set_region_and_endpoints(region['regionName'])
        search_vmclusters()

# -- If --database option specificed, run the search query/queries for ExaCC DB homes and save results in db_homes list
if display_dbs:
    if not(all_regions):
        search_db_homes()
    else:
        for region in regions:
            set_region_and_endpoints(region['regionName'])
            search_db_homes()

# -- Run the search query/queries for ExaCC autonomous VM clusters and save results in autonomousvmclusters list
if not(all_regions):
    search_autonomousvmclusters()
else:
    for region in regions:
        set_region_and_endpoints(region['regionName'])
        search_autonomousvmclusters()

# -- If --database option specificed:
# - run the search query/queries for ExaCC autonomous container databases and save results in auto_cdbs list
# - run the search query/queries for ExaCC autonomous databases and save results in auto_dbs list
if display_dbs:
    if not(all_regions):
        search_auto_cdbs()
        search_auto_dbs()
    else:
        for region in regions:
            set_region_and_endpoints(region['regionName'])
            search_auto_cdbs()
            search_auto_dbs()

# -- Generate HTML page with results
html_report = generate_html_report()

# -- Display HTML report 
print(html_report)

# -- Send HTML report by email if requested
if args.email:
    send_email(args.email, html_report)

# -- Store HTML report into an OCI object storage bucket (in the home region) if requested
if args.bucket_name:
    set_region_and_endpoints(home_region)
    store_report_in_bucket(args.bucket_name, html_report)

# -- the end
exit (0)
