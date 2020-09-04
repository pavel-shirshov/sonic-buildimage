"""
Implementation of "allow-list" feature
"""
import re

from app.log import log_debug, log_info, log_err, log_warn
from app.template import TemplateFabric
from app.manager import Manager
from app.util import run_command

class BGPAllowListMgr(Manager):
    """ This class initialize "AllowList" settings """
    ALLOW_ADDRESS_PL_NAME_TMPL = "ALLOW_ADDRESS_%d_%s"  # template for a name for the ALLOW_ADDRESS prefix-list ???
    EMPTY_COMMUNITY = "empty"
    PL_NAME_TMPL = "PL_ALLOW_LIST_DEPLOYMENT_ID_%d_COMMUNITY_%s_V%s"
    COMMUNITY_NAME_TMPL = "COMMUNITY_ALLOW_LIST_DEPLOYMENT_ID_%d_COMMUNITY_%s"
    RM_NAME_TMPL = "ALLOW_LIST_DEPLOYMENT_ID_%d_V%s"

    V4 = "v4"  # constant for af enum: V4
    V6 = "v6"  # constant for af enum: V6

    def __init__(self, common_objs, db, table):
        """
        Initialize the object
        :param common_objs: common object dictionary
        :param db: name of the db
        :param table: name of the table in the db
        """
        super(BGPAllowListMgr, self).__init__(
            common_objs,
            [],
            db,
            table,
        )
        self.cfg_mgr = common_objs["cfg_mgr"]
        self.constants = common_objs["constants"]
        self.key_re = re.compile(r"^DEPLOYMENT_ID\|\d+\|\S+$|^DEPLOYMENT_ID\|\d+$")
        self.enabled = self.__get_enabled()
        self.__load_constant_lists()

    def set_handler(self, key, data):
        """
        Manager method which runs on receiving 'SET' message
        :param key: ket of the 'SET' message
        :param data: data of the 'SET' message
        :return: True if the message was executed, False - the message should be postponed.
        """
        if not self.enabled:
            log_warn("BGPAllowListMgr::Received 'SET' command, but this feature is disabled in constants")
            return True
        if not self.__set_handler_validate(key, data):
            return True
        key = key.replace("DEPLOYMENT_ID|", "")
        deployment_id, community_value = key.split('|', 1) if '|' in key else (key, BGPAllowListMgr.EMPTY_COMMUNITY)
        deployment_id = int(deployment_id)
        prefixes_v4 = []
        prefixes_v6 = []
        if "prefixes_v4" in data:
            prefixes_v4 = str(data['prefixes_v4']).split(",")
        if "prefixes_v6" in data:
            prefixes_v6 = str(data['prefixes_v6']).split(",")
        self.__update_policy(deployment_id, community_value, prefixes_v4, prefixes_v6)
        return True

    def __set_handler_validate(self, key, data):
        """
        Validate parameters of a "Set" message
        :param key: ket of the 'SET' message
        :param data: data of the 'SET' message
        :return: True if parameters are valid, False if parameters are invalid
        """
        if data is None:
            log_err("BGPAllowListMgr::Received BGP ALLOWED 'SET' message without data")
            return False
        if not self.key_re.match(key):
            log_err("BGPAllowListMgr::Received BGP ALLOWED 'SET' message with invalid key: '%s'" % key)
            return False
        prefixes_v4 = []
        prefixes_v6 = []
        if "prefixes_v4" in data:
            prefixes_v4 = str(data["prefixes_v4"]).split(",")
            if not all(TemplateFabric.is_ipv4(prefix) for prefix in prefixes_v4):
                arguments = "prefixes_v4", str(data["prefixes_v4"])
                log_err("BGPAllowListMgr::Received BGP ALLOWED 'SET' message with invalid input[%s]:'%s'" % arguments)
                return False
        if "prefixes_v6" in data:
            prefixes_v6 = str(data["prefixes_v6"]).split(",")
            if not all(TemplateFabric.is_ipv6(prefix) for prefix in prefixes_v6):
                arguments = "prefixes_v6", str(data["prefixes_v6"])
                log_err("BGPAllowListMgr::Received BGP ALLOWED 'SET' message with invalid input[%s]:'%s'" % arguments)
                return False
        if not prefixes_v4 and not prefixes_v6:
            log_err("BGPAllowListMgr::Received BGP ALLOWED 'SET' message with no prefixes specified: %s" % str(data))
            return False
        return True

    def del_handler(self, key):
        """
        Manager method which runs on "DEL" message
        :param key: a key of "DEL" message
        """
        if not self.enabled:
            log_warn("BGPAllowListMgr::Received 'DEL' command, but this feature is disabled in constants")
            return
        if not self.__del_handler_validate(key):
            return
        key = key.replace('DEPLOYMENT_ID|', '')
        deployment_id, community = key.split('|', 1) if '|' in key else (key, BGPAllowListMgr.EMPTY_COMMUNITY)
        deployment_id = int(deployment_id)
        self.__remove_policy(deployment_id, community)

    def __del_handler_validate(self, key):
        """
        Validate "DEL" method parameters
        :param key: a key of "DEL" message
        :return: True if parameters are valid, False if parameters are invalid
        """
        if not self.key_re.match(key):
            log_err("BGPAllowListMgr::Received BGP ALLOWED 'DEL' message with invalid key: '$s'" % key)
            return False
        return True

    def __update_policy(self, deployment_id, community_value, prefixes_v4, prefixes_v6):
        """
        Update "allow list" policy with parameters
        :param deployment_id: deployment id which policy will be changed
        :param community_value: community value to match for the updated policy
        :param prefixes_v4: a list of v4 prefixes for the updated policy
        :param prefixes_v6: a list of v6 prefixes for the updated policy
        """
        # update all related entries with the information
        info = deployment_id, community_value, str(prefixes_v4), str(prefixes_v6)
        msg = "BGPAllowListMgr::Updating 'Allow list' policy."
        msg += " deployment_id '%s'. community: '%s'"
        msg += " prefix_v4 '%s'. prefix_v6: '%s'"
        log_info(msg % info)
        names = self.__generate_names(deployment_id, community_value)
        self.cfg_mgr.update()
        cmds = []
        cmds += self.__update_prefix_list(self.V4, names['pl_v4'], prefixes_v4)
        cmds += self.__update_prefix_list(self.V6, names['pl_v6'], prefixes_v6)
        cmds += self.__update_community(names['community'], community_value)
        cmds += self.__update_allow_route_map_entry(self.V4, names['pl_v4'], names['community'], names['rm_v4'])
        cmds += self.__update_allow_route_map_entry(self.V6, names['pl_v6'], names['community'], names['rm_v6'])
        if cmds:
            rc = self.cfg_mgr.push_list(cmds)
            rc = rc and self.__restart_peers(deployment_id)
            log_debug("BGPAllowListMgr::__update_policy. The peers were updated: rc=%s" % rc)
        else:
            log_debug("BGPAllowListMgr::__update_policy. Nothing to update")
        log_info("BGPAllowListMgr::Done")

    def __remove_policy(self, deployment_id, community_value):
        """
        Remove "allow list" policy for given deployment_id and community_value
        :param deployment_id: deployment id which policy will be removed
        :param community_value: community value to match for the removed policy
        """
        # remove all related entries from the configuration
        # put default rule to the route-map
        info = deployment_id, community_value
        msg = "BGPAllowListMgr::Removing 'Allow list' policy."
        msg += " deployment_id '%s'. community: '%s'"
        log_info(msg % info)

        names = self.__generate_names(deployment_id, community_value)
        self.cfg_mgr.update()
        cmds = []
        cmds += self.__remove_allow_route_map_entry(self.V4, names['pl_v4'], names['community'], names['rm_v4'])
        cmds += self.__remove_allow_route_map_entry(self.V6, names['pl_v6'], names['community'], names['rm_v6'])
        cmds += self.__remove_prefix_list(self.V4, names['pl_v4'])
        cmds += self.__remove_prefix_list(self.V6, names['pl_v6'])
        cmds += self.__remove_community(names['community'])
        if cmds:
            rc = self.cfg_mgr.push_list(cmds)
            rc = rc and self.__restart_peers(deployment_id)
            log_debug("BGPAllowListMgr::__remove_policy. 'Allow list' policy was removed. rc:%s" % rc)
        else:
            log_debug("BGPAllowListMgr::__remove_policy. Nothing to remove")
        log_info('BGPAllowListMgr::Done')

    @staticmethod
    def __generate_names(deployment_id, community_value):
        """
        Generate prefix-list names for a given peer_ip and community value
        :param deployment_id: deployment_id for which we're going to filter prefixes
        :param community_value: community, which we want to use to filter prefixes
        :return: a dictionary with names
        """
        if community_value == BGPAllowListMgr.EMPTY_COMMUNITY:
            community_name = BGPAllowListMgr.EMPTY_COMMUNITY
        else:
            community_name = BGPAllowListMgr.COMMUNITY_NAME_TMPL % (deployment_id, community_value)
        names = {
            "pl_v4": BGPAllowListMgr.PL_NAME_TMPL % (deployment_id, community_value, '4'),
            "pl_v6": BGPAllowListMgr.PL_NAME_TMPL % (deployment_id, community_value, '6'),
            "rm_v4": BGPAllowListMgr.RM_NAME_TMPL % (deployment_id, '4'),
            "rm_v6": BGPAllowListMgr.RM_NAME_TMPL % (deployment_id, '6'),
            "community": community_name,
        }
        arguments = deployment_id, community_value, str(names)
        log_debug("BGPAllowListMgr::__generate_names. deployment_id: %d, community: %s. names: %s" % arguments)
        return names

    def __update_prefix_list(self, af, pl_name, allow_list):
        """
        Create or update a prefix-list with name pl_name.
        :param af: "v4" to create ipv4 prefix-list, "v6" to create ipv6 prefix-list
        :param pl_name: prefix-list name
        :param allow_list: prefix-list entries
        :return: True if updating was successful, False otherwise
        """
        assert af == self.V4 or af == self.V6
        constant_list = self.__get_constant_list(af)
        allow_list = self.__to_prefix_list(allow_list)
        log_debug("BGPAllowListMgr::__update_prefix_list. af='%s' prefix-list name=%s" % (af, pl_name))
        exist, correct = self.__is_prefix_list_valid(af, pl_name, allow_list, constant_list)
        if correct:
            log_debug("BGPAllowListMgr::__update_prefix_list. the prefix-list '%s' exists and correct" % pl_name)
            return []
        family = self.__af_to_family(af)
        cmds = []
        seq_no = 10
        if exist:
            cmds.append('no %s prefix-list %s' % (family, pl_name))
        for entry in constant_list + allow_list:
            cmds.append('%s prefix-list %s seq %d %s' % (family, pl_name, seq_no, entry))
            seq_no += 10
        return cmds

    def __remove_prefix_list(self, af, pl_name):
        """
        Remove prefix-list in the address-family af.
        :param af: "v4" to create ipv4 prefix-list, "v6" to create ipv6 prefix-list
        :param pl_name: list of prefix-list names
        :return: True if operation was successful, False otherwise
        """
        assert af == self.V4 or af == self.V6
        log_debug("BGPAllowListMgr::__remove_prefix_lists. af='%s' pl_names='%s'" % (af, pl_name))
        exist, _ = self.__is_prefix_list_valid(af, pl_name, [], [])
        if not exist:
            log_debug("BGPAllowListMgr::__remove_prefix_lists: prefix_list '%s' not found" % pl_name)
            return []
        family = self.__af_to_family(af)
        return ["no %s prefix-list %s" % (family, pl_name)]

    def __is_prefix_list_valid(self, af, pl_name, allow_list, constant_list):
        """
        Check that a prefix list exists and it has valid entries
        :param af: address family of the checked prefix-list
        :param pl_name: prefix-list name
        :param allow_list: a prefix-list which must be a part of the valid prefix list
        :param constant_list: a constant list which must be on top of each "allow" prefix list on the device
        :return: a tuple. The first element of the tuple has True if the prefix-list exists, False otherwise,
                 The second element of the tuple has True if the prefix-list contains correct entries, False if not
        """
        assert af == self.V4 or af == self.V6
        family = self.__af_to_family(af)
        match_string = '%s prefix-list %s seq ' % (family, pl_name)
        conf = self.cfg_mgr.get_text()
        if not any(line.strip().startswith(match_string) for line in conf):
            return False, False  # if the prefix list is not exists, it is not correct
        constant_set = set(constant_list)
        allow_set = set(allow_list)
        for line in conf:
            if line.startswith(match_string):
                found = line[len(match_string):].strip().split(' ')
                rule = " ".join(found[1:])
                if rule in constant_set:
                    constant_set.discard(rule)
                elif rule in allow_set:
                    if constant_set:
                        return True, False  # Not everything from constant set is presented
                    else:
                        allow_set.discard(rule)
        return True, len(allow_set) == 0  # allow_set should be presented all

    def __update_community(self, community_name, community_value):
        """
        Update community for a peer
        :param community_name: name of the community to update
        :param community_value: community value for the peer
        :return: True if operation was successful, False otherwise
        """
        log_debug("BGPAllowListMgr::__update_community. community_name='%s' community='%s'" % (community_name, community_value))
        if community_value == self.EMPTY_COMMUNITY:  # we don't need to do anything for EMPTY community
            log_debug("BGPAllowListMgr::__update_community. Empty community. exiting")
            return []
        cmds = []
        exists, found_community_value = self.__is_community_presented(community_name)
        if exists:
            if community_value == found_community_value:
                log_debug("BGPAllowListMgr::__update_community. community '%s' is already presented" % community_name)
                return []
            else:
                msg = "BGPAllowListMgr::__update_community. "
                msg += "community '%s' is already presented, but community value should be updated" % community_name
                log_debug(msg)
                cmds.append("no bgp community-list standard %s" % community_name)
        cmds.append('bgp community-list standard %s permit %s' % (community_name, community_value))
        return cmds

    def __remove_community(self, community_name):
        """
        Remove community for a peer
        :param community_name: community value for the peer
        :return: True if operation was successful, False otherwise
        """
        log_debug("BGPAllowListMgr::__remove_community. community='%s'" % community_name)
        if community_name == self.EMPTY_COMMUNITY:  # we don't need to do anything for EMPTY community
            log_debug("BGPAllowListMgr::__remove_community. There is nothing to remove in empty community")
            return []
        exists, _ = self.__is_community_presented(community_name)
        if not exists:
            log_debug("BGPAllowListMgr::__remove_community. Community is already removed.")
            return []
        return ['no bgp community-list standard %s' % community_name]

    def __is_community_presented(self, community_name):
        """
        Return True if community for the peer_ip exists
        :param community_name: community value for the peer
        :return: A tuple. First element: True if operation was successful, False otherwise
                          Second element: community value if the first element is True no value otherwise
        """
        log_debug("BGPAllowListMgr::__is_community_presented. community='%s'" % community_name)
        match_string = 'bgp community-list standard %s permit ' % community_name
        conf = self.cfg_mgr.get_text()
        found = [line.strip() for line in conf if line.strip().startswith(match_string)]
        if not found:
            return False, None
        community_value = found[0].replace(match_string, '')
        return True, community_value

    def __update_allow_route_map_entry(self, af, allow_address_pl_name, community_name, route_map_name):
        """
        Add or update a "Allow address" route-map entry with the parameters
        :param af: "v4" to create ipv4 prefix-list, "v6" to create ipv6 prefix-list
        :return: True if operation was successful, False otherwise
        """
        assert af == self.V4 or af == self.V6
        info = af, route_map_name, allow_address_pl_name, community_name
        log_debug("BGPAllowListMgr::__update_allow_route_map_entry. af='%s' Allow rm='%s' pl='%s' cl='%s'" % info)
        entries = self.__parse_allow_route_map_entries(af, route_map_name)
        found, _ = self.__find_route_map_entry(entries, allow_address_pl_name, community_name)
        if found:
            log_debug("BGPAllowListMgr::__update_allow_route_map_entry. route-map='%s' is already found" % route_map_name)
            return []
        seq_number = self.__find_next_seq_number(entries.keys(), community_name != self.EMPTY_COMMUNITY, route_map_name)
        info = af, seq_number, allow_address_pl_name, community_name
        out = "af='%s' seqno='%d' Allow pl='%s' cl='%s'" % info
        log_debug("BGPAllowListMgr::__update_allow_route_map_entry. %s" % out)
        ip_version = "" if af == self.V4 else "v6"
        cmds = [
            'route-map %s permit %d' % (route_map_name, seq_number),
            ' match ip%s address prefix-list %s' % (ip_version, allow_address_pl_name)
        ]
        if not community_name.endswith(self.EMPTY_COMMUNITY):
            cmds.append(" match community %s" % community_name)
        return cmds

    def __remove_allow_route_map_entry(self, af, allow_address_pl_name, community_name, route_map_name):
        """
        Add or update a "Allow address" route-map entry with the parameters
        :param af: "v4" to create ipv4 prefix-list, "v6" to create ipv6 prefix-list
        :return: True if operation was successful, False otherwise
        """
        assert af == self.V4 or af == self.V6
        info = af, route_map_name, allow_address_pl_name, community_name
        log_debug("BGPAllowListMgr::__update_allow_route_map_entry. af='%s' Allow rm='%s' pl='%s' cl='%s'" % info)
        entries = self.__parse_allow_route_map_entries(af, route_map_name)
        found, seq_number = self.__find_route_map_entry(entries, allow_address_pl_name, community_name)
        if not found:
            log_debug("BGPAllowListMgr::__update_allow_route_map_entry. Not found route-map '%s' entry" % allow_address_pl_name)
            return []
        return ['no route-map %s permit %d' % (route_map_name, seq_number)]

    @staticmethod
    def __find_route_map_entry(entries, allow_address_pl_name, community_name):
        """
        Find route-map entry with given allow_address prefix list name and community name in the parsed route-map.
        :param entries: entries of parsed route-map
        :param allow_address_pl_name: name of the "allow address" prefix-list
        :param community_name: name of the "allow address" community name
        :return: a tuple. The first element of the tuple is True, if the route-map entry was found, False otherwise.
                          The second element of the tuple has a sequence number of the entry.
        """
        for sequence_number, values in entries.items():
            if sequence_number == 65535:
                continue
            allow_list_presented = values['pl_allow_list'] == allow_address_pl_name
            community_presented = values['community'] == community_name
            if allow_list_presented and community_presented:
                log_debug("BGPAllowListMgr::__find_route_map_entry. found route-map '%s' entry" % allow_address_pl_name)
                return True, sequence_number
        return False, None

    def __parse_allow_route_map_entries(self, af, route_map_name):
        """
        Parse "Allow list" route-map entries.
        :param af: "v4" to create ipv4 prefix-list, "v6" to create ipv6 prefix-list
        :return: A tuple, First element: True if operation was successful, False otherwise
                          Second element: list of object with parsed route-map entries
        """
        assert af == self.V4 or af == self.V6
        log_debug("BGPAllowListMgr::__parse_allow_route_map_entries. af='%s', rm='%s'" % (af, route_map_name))
        match_string = 'route-map %s permit ' % route_map_name
        entries = {}
        inside_route_map = False
        route_map_seq_number = None
        pl_allow_list_name = None
        community_name = self.EMPTY_COMMUNITY
        if af == self.V4:
            match_pl_allow_list = 'match ip address prefix-list '
        else:  # self.V6
            match_pl_allow_list = 'match ipv6 address prefix-list '
        match_community = 'match community '
        conf = self.cfg_mgr.get_text()
        for line in conf + [""]:
            if inside_route_map:
                if line.strip().startswith(match_pl_allow_list):
                    pl_allow_list_name = line.strip()[len(match_pl_allow_list):]
                    continue
                elif line.strip().startswith(match_community):
                    community_name = line.strip()[len(match_community):]
                    continue
                else:
                    if pl_allow_list_name is not None:
                        entries[route_map_seq_number] = {
                            'pl_allow_list': pl_allow_list_name,
                            'community': community_name,
                        }
                    else:
                        log_warn("BGPAllowListMgr::Found incomplete route-map '%s' entry. seq_no=%d" % (route_map_name, route_map_seq_number))
                    inside_route_map = False
                    pl_allow_list_name = None
                    community_name = self.EMPTY_COMMUNITY
                    route_map_seq_number = None
            if line.startswith(match_string):
                found = line[len(match_string):]
                assert found.isdigit()
                route_map_seq_number = int(found)
                inside_route_map = True
        return entries

    @staticmethod
    def __find_next_seq_number(seq_numbers, has_community, route_map_name):
        """
        Find a next available "Allow list" route-map entry number
        :param seq_numbers: a list of already used sequence numbers
        :param has_community: True, if the route-map entry has community
        :return: next available route-map sequence number
        """
        used_sequence_numbers = set(seq_numbers)
        sequence_number = None
        if has_community:  # put entries without communities after 32768
            start_seq = 10
            end_seq = 29990
        else:
            start_seq = 30000
            end_seq = 65530
        for i in range(start_seq, end_seq, 10):
            if i not in used_sequence_numbers:
                sequence_number = i
                break
        if sequence_number is None:
            raise RuntimeError("No free sequence numbers for '%s'" % route_map_name)
        info = sequence_number, "yes" if has_community else "no"
        log_debug("BGPAllowListMgr::__find_next_seq_number '%d' has_community='%s'" % info)
        return sequence_number

    @staticmethod
    def __restart_peers(deployment_id):
        """
        Restart peers with deployment_id
        :param deployment_id: deployment_id number
        """
        log_info("BGPAllowListMgr::Restart peers with deployment_id=%d" % deployment_id)
        no_error, _, _ = run_command(["vtysh", "-c", "clear bgp * soft in"])
        return no_error

    def __get_enabled(self):
        """
        Load enable/disabled property from constants
        :return: True if enabled, False otherwise
        """
        return 'bgp' in self.constants \
           and 'allow_list' in self.constants["bgp"] \
           and "enabled" in self.constants["bgp"]["allow_list"] \
           and self.constants["bgp"]["allow_list"]["enabled"]

    def __load_constant_lists(self):
        """
        Load default prefix-list entries from constants.yml file
        """
        if 'bgp' in self.constants and 'allow_list' in self.constants["bgp"] \
                and "default_pl_rules" in self.constants["bgp"]["allow_list"]:
            obj = self.constants["bgp"]["allow_list"]["default_pl_rules"]
            if "v4" in obj:
                self.constants_v4 = obj["v4"]
            else:
                self.constants_v4 = []
            if "v6" in obj:
                self.constants_v6 = obj["v6"]
            else:
                self.constants_v6 = []

    def __get_constant_list(self, af):
        """
        Return loaded default prefix-list entries bases on address family
        :param af: address family
        :return: default prefix-list entries
        """
        if af == self.V4:
            return self.constants_v4
        else:
            return self.constants_v6

    @staticmethod
    def __to_prefix_list(allow_list):
        """
        Convert "allow list" prefix list, to a prefix-list rules
        :param allow_list: "allow list" prefix list
        :return: prefix-list rules
        """
        return ["permit %s ge %d" % (prefix, int(prefix.split("/")[1])+1) for prefix in allow_list]

    def __af_to_family(self, af):
        """
        Convert address family into prefix list family
        :param af: address family
        :return: prefix list ip family
        """
        return 'ip' if af == self.V4 else 'ipv6'