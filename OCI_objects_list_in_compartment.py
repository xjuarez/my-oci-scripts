# --------------------------------------------------------------------------------------------------------------------------
# This script lists all objects (detailed list below) in a given compartment in a region or all active regions using OCI CLI
#
# Supported objects:
# - COMPUTE            : compute instances, custom images, boot volumes, boot volumes backups
# - BLOCK STORAGE      : block volumes, block volumes backups, volume groups, volume groups backups
# - OBJECT STORAGE     : buckets
# - FILE STORAGE       : file systems, mount targets
# - NETWORKING         : VCN, DRG, CPE, IPsec connection, LB, public IPs, DNS zones (common to all regions)
# - DATABASE           : DB Systems, DB Systems backups, Autonomous DB, Autonomous DB backups
# - RESOURCE MANAGER   : Stacks
# - DEVELOPER SERVICES : Container clusters (OKE)
# - IDENTITY           : Policies (common to all regions)
# - GOVERNANCE         : Tags namespaces (common to all regions)
#
# Note: OCI tenant and region given by an OCI CLI PROFILE
# Author        : Christophe Pauliat with some help from Matthieu Bordonne
# Platforms     : MacOS / Linux
#
# prerequisites : - Python 3 with OCI Python SDK installed
#                 - OCI config file configured with profiles
# Versions
#    2020-01-02: Initial Version
# --------------------------------------------------------------------------------------------------------------------------

# -- import
import oci
import sys
import argparse

# ---------- Colors for output
# see https://misc.flogisoft.com/bash/tip_colors_and_formatting to customize
colored_output=True
if (colored_output):
  COLOR_TITLE0="\033[95m"             # light magenta
  COLOR_TITLE1="\033[91m"             # light red
  COLOR_TITLE2="\033[32m"             # green
  COLOR_AD="\033[94m"                 # light blue
  COLOR_COMP="\033[93m"               # light yellow
  COLOR_BREAK="\033[91m"              # light red
  COLOR_NORMAL="\033[39m"
else:
  COLOR_TITLE0=""
  COLOR_TITLE1=""
  COLOR_TITLE2=""
  COLOR_AD=""
  COLOR_COMP=""
  COLOR_BREAK=""
  COLOR_NORMAL=""

# ---------- Functions

# -- variables
configfile = "~/.oci/config"    # Define config file to be used.

# -- usage syntax
def usage():
    print ("Usage: python3 {} [-a] [-r] OCI_PROFILE compartment_ocid".format(sys.argv[0]))
    print ("    or python3 {} [-a] [-r] OCI_PROFILE compartment_name".format(sys.argv[0]))
    print ("")
    print ("    By default, only the objects in the region provided in the profile are listed")
    print ("    If -a is provided, the objects from all subscribed regions are listed")
    print ("    If -r is provided (recursive option), objects in active sub-compartments will also be listed")
    print ("")
    print ("note: OCI_PROFILE must exist in {} file (see example below)".format(configfile))
    print ("")
    print ("[EMEAOSCf]")
    print ("tenancy     = ocid1.tenancy.oc1..aaaaaaaaw7e6nkszrry6d5hxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print ("user        = ocid1.user.oc1..aaaaaaaayblfepjieoxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print ("fingerprint = 19:1d:7b:3a:17:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx")
    print ("key_file    = /Users/cpauliat/.oci/api_key.pem")
    print ("region      = eu-frankfurt-1")
    exit (1)

# -- Networking
def list_networking_dns_zones(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: DNS zones "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(DnsClient.list_zones,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for zone in response.data:
            print ('{0:s}'.format(zone.name))

def list_identity_policies(lcpt_ocid):
    print (COLOR_TITLE2+"========== IDENTITY: Policies "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(IdentityClient.list_policies,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for policy in response.data:
            print ('{0:s}'.format(policy.name))

def list_governance_tag_namespaces(lcpt_ocid):
    print (COLOR_TITLE2+"========== GOVERNANCE: Tag Namespaces "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(IdentityClient.list_tag_namespaces,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for tag_namespace in response.data:
            print ('{0:s}'.format(tag_namespace.name))

# -- List objects common to all regions
def list_objects_common_to_all_regions(cpt_ocid,cpt_name):
    global DnsClient

    print (COLOR_TITLE1+"==================== BEGIN: objects common to all regions in compartment "+COLOR_COMP+"{} ".format(cpt_name)+COLOR_NORMAL)
    
    # DNS
    DnsClient = oci.dns.DnsClient(config)
    list_networking_dns_zones (cpt_ocid)

    # Identity
    list_identity_policies (cpt_ocid)
    list_governance_tag_namespaces (cpt_ocid)

    print (COLOR_TITLE1+"==================== END: objects common to all regions in compartment "+COLOR_COMP+"{} ".format(cpt_name)+COLOR_NORMAL)

    # if requested, also process active sub-compartments
    if (include_sub_cpt):
        response = oci.pagination.list_call_get_all_results(IdentityClient.list_compartments, cpt_ocid)
        sub_compartments = response.data
        for sub_compartment in sub_compartments:
            if (sub_compartment.lifecycle_state == "ACTIVE"):
                list_objects_common_to_all_regions(sub_compartment.id,sub_compartment.name)

# -- Compute
def list_compute_instances (lcpt_ocid):
    print (COLOR_TITLE2+"========== COMPUTE: Instances "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(ComputeClient.list_instances,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for instance in response.data:
            print ('{0:15s} {1:20s} {2:50s}'.format(instance.display_name, instance.shape, instance.id))

def list_compute_custom_images(lcpt_ocid):
    print (COLOR_TITLE2+"========== COMPUTE: Custom Images "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(ComputeClient.list_images,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for image in response.data:
            print ('{0:s}'.format(image.display_name))

def list_compute_boot_volumes(lcpt_ocid):
    print (COLOR_TITLE2+"========== COMPUTE: Boot Volumes "+COLOR_NORMAL)
    for ad in ads:
        print (COLOR_AD+"== Availability-domain {:s}".format(ad.name)+COLOR_NORMAL)

        response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_boot_volumes,availability_domain=ad.name,compartment_id=lcpt_ocid)
        if len(response.data) > 0:
            for bootvol in response.data:
                print ('{0:s}'.format(bootvol.display_name))

def list_compute_boot_volume_backups(lcpt_ocid):
    print (COLOR_TITLE2+"========== COMPUTE: Boot Volume Backups "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_boot_volume_backups,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for bootvol_backup in response.data:
            print ('{0:s}'.format(bootvol_backup.display_name))

# -- Block Storage
def list_block_storage_volumes(lcpt_ocid):
    print (COLOR_TITLE2+"========== BLOCK STORAGE: Block volumes "+COLOR_NORMAL)
    for ad in ads:
        print (COLOR_AD+"== Availability-domain {:s}".format(ad.name)+COLOR_NORMAL)

        response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_volumes,availability_domain=ad.name,compartment_id=lcpt_ocid)
        if len(response.data) > 0:
            for bkvol in response.data:
                print ('{0:s}'.format(bkvol.display_name))

def list_block_storage_volume_backups(lcpt_ocid):
    print (COLOR_TITLE2+"========== BLOCK STORAGE: Block volume backups "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_volume_backups,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for bkvol_backup in response.data:
            print ('{0:s}'.format(bkvol_backup.display_name))

def list_block_storage_volume_groups(lcpt_ocid):
    print (COLOR_TITLE2+"========== BLOCK STORAGE: Volumes groups "+COLOR_NORMAL)
    for ad in ads:
        print (COLOR_AD+"== Availability-domain {:s}".format(ad.name)+COLOR_NORMAL)

        response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_volume_groups,availability_domain=ad.name,compartment_id=lcpt_ocid)
        if len(response.data) > 0:
            for vg in response.data:
                print ('{0:s}'.format(vg.display_name))

def list_block_storage_volume_group_backups(lcpt_ocid):
    print (COLOR_TITLE2+"========== BLOCK STORAGE: Volumes group backups "+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(BlockstorageClient.list_volume_group_backups,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for vg_backup in response.data:
            print ('{0:s}'.format(vg_backup.display_name))

# -- Object Storage
def list_object_storage_buckets(lcpt_ocid):
    namespace = ObjectStorageClient.get_namespace().data
    print (COLOR_TITLE2+"========== OBJECT STORAGE: Buckets (namespace {})".format(namespace)+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(ObjectStorageClient.list_buckets,namespace_name=namespace,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for bucket in response.data:
            print ('{0:s}'.format(bucket.name))

# -- File Storage
def list_file_storage_filesystems(lcpt_ocid):
    print (COLOR_TITLE2+"========== FILE STORAGE: Filesystems "+COLOR_NORMAL)
    for ad in ads:
        print (COLOR_AD+"== Availability-domain {:s}".format(ad.name)+COLOR_NORMAL)

        response = oci.pagination.list_call_get_all_results(FileStorageClient.list_file_systems,availability_domain=ad.name,compartment_id=lcpt_ocid)
        if len(response.data) > 0:
            for fs in response.data:
                print ('{0:s}'.format(fs.display_name))

def list_file_storage_mount_targets(lcpt_ocid):
    print (COLOR_TITLE2+"========== FILE STORAGE: Mount targets "+COLOR_NORMAL)
    for ad in ads:
        print (COLOR_AD+"== Availability-domain {:s}".format(ad.name)+COLOR_NORMAL)

        response = oci.pagination.list_call_get_all_results(FileStorageClient.list_mount_targets,availability_domain=ad.name,compartment_id=lcpt_ocid)
        if len(response.data) > 0:
            for mt in response.data:
                print ('{0:s}'.format(mt.display_name))

# -- Networking
def list_networking_vcns(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: Virtal Cloud Networks (VCNs)"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(VirtualNetworkClient.list_vcns,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for vcn in response.data:
            print ('{0:s}'.format(vcn.display_name))

def list_networking_drgs(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: Dynamic Routing Gateways (DRGs)"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(VirtualNetworkClient.list_drgs,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for drg in response.data:
            print ('{0:s}'.format(drg.display_name))

def list_networking_cpes(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: Customer Premises Equipments (CPEs)"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(VirtualNetworkClient.list_cpes,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for cpe in response.data:
            print ('{0:s}'.format(cpe.display_name))

def list_networking_ipsecs(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: IPsec connections"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(VirtualNetworkClient.list_ip_sec_connections,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for ipsec in response.data:
            print ('{0:s}'.format(ipsec.display_name))

def list_networking_lbs(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: Load balancers"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(LoadBalancerClient.list_load_balancers,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for lb in response.data:
            print ('{0:s}'.format(lb.display_name))

def list_networking_public_ips(lcpt_ocid):
    print (COLOR_TITLE2+"========== NETWORKING: Reserved Public IPs"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(VirtualNetworkClient.list_public_ips,scope="REGION",lifetime="RESERVED",compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for ip in response.data:
            print ('{0:s}'.format(ip.display_name))

# -- Database
def list_database_db_systems(lcpt_ocid):
    print (COLOR_TITLE2+"========== DATABASE: DB Systems"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(DatabaseClient.list_db_systems,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for dbs in response.data:
            print ('{0:s}'.format(dbs.display_name))

def list_database_db_systems_backups(lcpt_ocid):
    print (COLOR_TITLE2+"========== DATABASE: DB Systems backups"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(DatabaseClient.list_backups,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for dbs in response.data:
            print ('{0:s}'.format(dbs.display_name))

def list_database_autonomous_db(lcpt_ocid):
    print (COLOR_TITLE2+"========== DATABASE: Autonomous databases (ATP/ADW)"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(DatabaseClient.list_autonomous_databases,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for adb in response.data:
            print ('{0:s}'.format(adb.display_name))

def list_database_autonomous_backups(lcpt_ocid):
    print (COLOR_TITLE2+"========== DATABASE: Autonomous databases backups"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(DatabaseClient.list_autonomous_database_backups,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for adb_backup in response.data:
            print ('{0:s}'.format(adb_backup.display_name))

# -- Resource manager
def list_resource_manager_stacks(lcpt_ocid):
    print (COLOR_TITLE2+"========== RESOURCE MANAGER: Stacks"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(ResourceManagerClient.list_stacks,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for stack in response.data:
            print ('{0:s}'.format(stack.display_name))

# -- Developer services
def list_developer_services_oke(lcpt_ocid):
    print (COLOR_TITLE2+"========== DEVELOPER SERVICES: Container clusters (OKE)"+COLOR_NORMAL)
    response = oci.pagination.list_call_get_all_results(ContainerEngineClient.list_clusters,compartment_id=lcpt_ocid)
    if len(response.data) > 0:
        for cluster in response.data:
            print ('{0:s}'.format(cluster.display_name))

# -- List region specific objects
def list_region_specific_objects (cpt_ocid,cpt_name):
    global ComputeClient
    global BlockstorageClient
    global ObjectStorageClient
    global FileStorageClient
    global VirtualNetworkClient
    global LoadBalancerClient
    global DatabaseClient
    global ResourceManagerClient
    global ContainerEngineClient

    print (COLOR_TITLE1+"==================== BEGIN: objects specific to region "+COLOR_COMP+config["region"]+COLOR_TITLE1+" in compartment "+COLOR_COMP+"{} ".format(cpt_name)+COLOR_NORMAL)

    # Compute
    ComputeClient = oci.core.ComputeClient(config)
    list_compute_instances (cpt_ocid)
    list_compute_custom_images (cpt_ocid)
 
    # Block Storage
    BlockstorageClient = oci.core.BlockstorageClient(config)
    list_compute_boot_volumes (cpt_ocid)
    list_compute_boot_volume_backups (cpt_ocid)
    list_block_storage_volumes (cpt_ocid)
    list_block_storage_volume_backups (cpt_ocid)
    list_block_storage_volume_groups (cpt_ocid)
    list_block_storage_volume_group_backups (cpt_ocid)

    # Object Storage
    ObjectStorageClient = oci.object_storage.ObjectStorageClient(config)
    list_object_storage_buckets (cpt_ocid)

    # File Storage
    FileStorageClient = oci.file_storage.FileStorageClient(config)
    list_file_storage_filesystems (cpt_ocid)
    list_file_storage_mount_targets (cpt_ocid)

    # Networking
    VirtualNetworkClient = oci.core.VirtualNetworkClient(config)
    LoadBalancerClient = oci.load_balancer.LoadBalancerClient(config)
    list_networking_vcns (cpt_ocid)
    list_networking_drgs (cpt_ocid)
    list_networking_cpes (cpt_ocid)
    list_networking_ipsecs (cpt_ocid)
    list_networking_lbs (cpt_ocid)
    list_networking_public_ips (cpt_ocid)

    # Database
    DatabaseClient = oci.database.DatabaseClient(config)
    list_database_db_systems (cpt_ocid)
    list_database_db_systems_backups (cpt_ocid)
    list_database_autonomous_db (cpt_ocid)
    list_database_autonomous_backups (cpt_ocid)

    # Resource Manager
    ResourceManagerClient = oci.resource_manager.ResourceManagerClient(config)
    list_resource_manager_stacks (cpt_ocid)

    # Developer Services
    ContainerEngineClient = oci.container_engine.ContainerEngineClient(config)
    list_developer_services_oke (cpt_ocid)

    print (COLOR_TITLE1+"==================== END: objects specific to region "+COLOR_COMP+config["region"]+COLOR_TITLE1+" in compartment "+COLOR_COMP+"{} ".format(cpt_name)+COLOR_NORMAL)

    # if requested, also process active sub-compartments
    if (include_sub_cpt):
        response = oci.pagination.list_call_get_all_results(IdentityClient.list_compartments, cpt_ocid)
        sub_compartments = response.data
        for sub_compartment in sub_compartments:
            if (sub_compartment.lifecycle_state == "ACTIVE"):
                list_region_specific_objects(sub_compartment.id,sub_compartment.name)

# ------------ main
global config
global ads
global IdentityClient
global initial_cpt_ocid
global initial_cpt_name

# -- parse arguments
all_regions = False
include_sub_cpt = False

if len(sys.argv) == 3:
    profile  = sys.argv[1] 
    cpt      = sys.argv[2]
elif len(sys.argv) == 4:
    profile  = sys.argv[2] 
    cpt      = sys.argv[3]
    if sys.argv[1] == "-a":
        all_regions = True
    elif sys.argv[1] == "-r":
        include_sub_cpt = True
    else:
        usage ()
elif len(sys.argv) == 5:
    profile  = sys.argv[3] 
    cpt      = sys.argv[4]
    if (sys.argv[1] == "-a" and sys.argv[2] == "-r") or (sys.argv[1] == "-r" and sys.argv[2] == "-a"):
        all_regions = True
        include_sub_cpt = True
    else:
        usage ()

# -- load profile from config file
try:
    config = oci.config.from_file(configfile,profile)

except:
    print ("ERROR 02: profile '{}' not found in config file {} !".format(profile,configfile))
    exit (2)

IdentityClient = oci.identity.IdentityClient(config)
user = IdentityClient.get_user(config["user"]).data
RootCompartmentID = user.compartment_id

# -- get list of compartments
response = oci.pagination.list_call_get_all_results(IdentityClient.list_compartments, RootCompartmentID,compartment_id_in_subtree=True)
compartments = response.data
cpt_exist = False
for compartment in compartments:  
    if (cpt == compartment.id) or (cpt == compartment.name):
        initial_cpt_ocid = compartment.id
        initial_cpt_name = compartment.name
        cpt_exist = True
if not(cpt_exist):
    print ("ERROR 03: compartment '{}' does not exist !".format(cpt))
    exit (3) 

# -- get list of subscribed regions
response = oci.pagination.list_call_get_all_results(IdentityClient.list_region_subscriptions, RootCompartmentID)
regions = response.data

# -- get list of ADs
response = oci.pagination.list_call_get_all_results(IdentityClient.list_availability_domains, RootCompartmentID)
ads = response.data

# -- list objects
if (all_regions):
    print (COLOR_TITLE1+"==================== List of subscribed regions in tenancy "+COLOR_NORMAL)
    for region in regions:
        print (region.region_name)

list_objects_common_to_all_regions(initial_cpt_ocid,initial_cpt_name)

if not(all_regions):
    list_region_specific_objects(initial_cpt_ocid,initial_cpt_name)
else:
    for region in regions:
        config["region"]=region.region_name
        list_region_specific_objects(initial_cpt_ocid,initial_cpt_name)

# -- the end
exit (0)