from collections import defaultdict
import re
import jinja2
from swsscommon import swsscommon

from .log import log_err, log_warn, log_info
from .manager import Manager


class BBRMgr(Manager):
    """ This class initialize "BBR" feature for  """
    def __init__(self, common_objs, db, table):
        """
        Initialize the object
        :param common_objs: common object dictionary
        :param db: name of the db
        :param table: name of the table in the db
        """
        super(BBRMgr, self).__init__(
            common_objs,
            [("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME, "localhost/bgp_asn"),],
            db,
            table,
        )
        self.enabled = False
        self.init()

# FIXME: set_handler when put more neighbours.

    def set_handler(self, key, data):
        """ Implementation of 'SET' command for this class """
        if key != 'all':
            log_err("Invalid key '%s' for table '%s'. The key should be 'all'" % (key, self.table_name))
            return True
        if 'status' not in data or data['status'] != "enabled" or data['status'] != "disabled":
            log_err("Invalid value '%s' for table '%s', key '%s'" % (data, self.table_name, key))
            return True
        self.directory.put(self.db_name, self.table_name, 'status', data['status'])
        #
        if not self.directory.available('LOCAL', "BBR_peer-group"):
            log_info("No BBR data collected yet")
            return False

        peer_groups = self.directory.get_slot('LOCAL', "BBR_peer-group")
        prefix_of_commands = "" if data['status'] == "enabled" else "no "
        bgp_asn = self.directory.get_slot("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME)["localhost"]["bgp_asn"]
        cmds = ["router bgp %s" % bgp_asn]
        for af in ["ipv4", "ipv6"]:
            cmds.append(" address-family %s" % af)
            for peer_group in peer_groups:
                cmds.append("%sneighbor %s allowas-in 1" % (prefix_of_commands, peer_group))
        self.cfg_mgr.push_list(cmds)
        return True

    def del_handler(self, key):
        """ Implementation of 'DEL' command for this class """
        self.directory.put(self.db_name, self.table_name, 'status', "disabled")
        log_warn("The '%s' table shouldn't be removed from the db" % self.table_name)

    def init(self):
        if 'bgp' in self.constants and \
                'bbr' in self.constants['bgp'] and \
                'enabled' in self.constants['bgp']['bbr'] and \
                self.constants['bgp']['bbr']['enabled']:
            self.enabled = True
            value = "enabled"
        else:
            self.enabled = False
            value = "disabled"
        self.directory.put(self.db_name, self.table_name, 'status', value)
        # FIXME: update db if it doesn't exist

def filter_bbr_config(text):
    # filter only allows and address-family
    res = defaultdict(list)
    address_family_re = re.compile(r'^\s*address-family (ipv[46])\s*$')
    allowas_in_re = re.compile(r'^\s+neighbor\s+(\S+)\s+allowas-in 1$')
    address_family = None
    for line in text.split("\n"):
        address_family_match = address_family_re.match(line)
        allowas_in_match = allowas_in_re.match(line)
        if address_family_match:
            address_family = address_family_match.group(1)
        elif allowas_in_match:
            peer_group = allowas_in_match.group(1)
            if address_family:
                res[peer_group].append(address_family)
            else:
                log_warn("BBR parser. no address family for '%s' allowas-in" % peer_group)
    return res

def generate_config(template, kwargs, bbr_value):
    kwargs['CONFIG_DB__BGP_BBR']['status'] = bbr_value
    txt = ""
    try:
        txt = template.render(**kwargs)
    except jinja2.TemplateError as e:
        log_err("Can't render policy template to check bbr: %s" % str(e))
    return txt

def compare_configs(enabled_config, disabled_config):
    bbr_enabled_peer_groups = {}
    for peer_group, enabled_afs in enabled_config.items():
        if peer_group in disabled_config:
            disabled_afs = disabled_config[peer_group]
            if sorted(enabled_afs) != sorted(disabled_afs):
                final_afs = list(set(enabled_afs) - set(disabled_afs))
                bbr_enabled_peer_groups[peer_group] = final_afs
        else:
            bbr_enabled_peer_groups[peer_group] = enabled_afs
    return bbr_enabled_peer_groups

def update_directory(directory, bbr_enabled_peer_groups):
    if directory.available('LOCAL', "BBR_peer-group"):
        from_directory = directory.get_slot('LOCAL', "BBR_peer-group")
    else:
        from_directory = {}
    for key, value in bbr_enabled_peer_groups.items():
        if key not in from_directory or key in from_directory and value != from_directory[key]:
            directory.put('LOCAL', "BBR_peer-group", key, value)

def extract_bbr_settings(directory, template, kwargs):
    #
    enabled_bbr_config = generate_config(template, kwargs, "enabled")
    disabled_bbr_config = generate_config(template, kwargs, "disabled")
    #
    enabled_config = filter_bbr_config(enabled_bbr_config)
    disabled_config = filter_bbr_config(disabled_bbr_config)
    #
    bbr_enabled_peer_groups = compare_configs(enabled_config, disabled_config)
    # FIXME: check that the groups are ipv4, ipv6 only
    update_directory(directory, bbr_enabled_peer_groups)
