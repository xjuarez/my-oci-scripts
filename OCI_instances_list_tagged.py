#!/usr/bin/env python3

# --------------------------------------------------------------------------------------------------------------------------
# This script looks for all compute instances in a tenant and region (all compartments)
# and list the tag values for the ones having specific tag namespace and tag key
#
# Note: OCI tenant and region given by an OCI CLI PROFILE
# Author        : Christophe Pauliat
# Platforms     : MacOS / Linux
#
# prerequisites : - Python 3 with OCI Python SDK installed
#                 - OCI config file configured with profiles
# Versions
#    2020-04-16: Initial Version
# --------------------------------------------------------------------------------------------------------------------------

# -- import
import oci
import sys

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

# ---- variables
configfile = "~/.oci/config"    # Define config file to be used.

# ---- usage syntax
def usage():
    print ("Usage: {} [-a] OCI_PROFILE tag_namespace tag_key".format(sys.argv[0]))
    print ("")
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

# -- Compute
def list_tagged_compute_instances_in_compartment (lcpt):
    if lcpt.lifecycle_state == "DELETED": return

    #print ("--- DEBUG: cpt=",lcpt.name, lcpt.lifecycle_state)
    # get the list of instances in this compartment
    response = oci.pagination.list_call_get_all_results(ComputeClient.list_instances,compartment_id=lcpt.id)
    if len(response.data) > 0:
        for instance in response.data:
            try:
                tag_value = instance.defined_tags[tag_ns][tag_key]
                print ('{:s}, {:s}, {:s}, {:s}.{:s} = {:s}'.format(lcpt.name, instance.display_name, instance.id, tag_ns, tag_key, tag_value))
            except:
                pass


# ------------ main
global config

# -- parse arguments
all_regions = False

if len(sys.argv) == 4:
    profile  = sys.argv[1] 
    tag_ns   = sys.argv[2]
    tag_key  = sys.argv[3]
elif len(sys.argv) == 5:
    if sys.argv[1] == "-a":
        all_regions = True
    else:
        usage()
    profile  = sys.argv[2] 
    tag_ns   = sys.argv[3]
    tag_key  = sys.argv[4]
else:
    usage()

# -- load profile from config file
try:
    config = oci.config.from_file(configfile,profile)

except:
    print ("ERROR 02: profile '{}' not found in config file {} !".format(profile,configfile))
    exit (2)

IdentityClient = oci.identity.IdentityClient(config)
user = IdentityClient.get_user(config["user"]).data
RootCompartmentID = user.compartment_id

# -- get list of subscribed regions
response = oci.pagination.list_call_get_all_results(IdentityClient.list_region_subscriptions, RootCompartmentID)
regions = response.data

# -- get compartments list
response = oci.pagination.list_call_get_all_results(IdentityClient.list_compartments, RootCompartmentID,compartment_id_in_subtree=True)
compartments = response.data

# -- ComputeClient
ComputeClient = oci.core.ComputeClient(config)

# -- list objects
#reg = 
for cpt in compartments:
    list_tagged_compute_instances_in_compartment (cpt)

# -- the end
exit (0)