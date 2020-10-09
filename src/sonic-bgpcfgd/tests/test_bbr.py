from bgpcfgd.template import TemplateFabric
from bgpcfgd.managers_bbr import filter_bbr_config, generate_config, compare_configs, update_directory, extract_bbr_settings
from mock import MagicMock, patch

import os

global_constants = {
    "bgp": {
        "allow_list": {
            "enabled": True,
            "default_pl_rules": {
                "v4": [ "deny 0.0.0.0/0 le 17" ],
                "v6": [
                    "deny 0::/0 le 59",
                    "deny 0::/0 ge 65"
                ]
            }
        }
    }
}

def prepare_for_render(value):
    kwargs = {
        'CONFIG_DB__DEVICE_METADATA': {'localhost': {'type': 'LeafRouter'}},
        'CONFIG_DB__BGP_BBR': {'status': value},
        'constants': global_constants,
        'bgp_asn': 65500,
        'vrf': "default",
        'neighbor_addr': "10.0.0.0",
        'bgp_session': {},
        'loopback0_ipv4': "1.1.1.1",
    }
    TEMPLATE_PATH = os.path.abspath('../../dockers/docker-fpm-frr/frr')
    tf = TemplateFabric(TEMPLATE_PATH)
    template = tf.from_file("bgpd/templates/general/peer-group.conf.j2")
    return template, kwargs

def test_filter_bbr_config_enabled():
    template, kwargs = prepare_for_render("enabled")
    txt = template.render(**kwargs)
    filtered = filter_bbr_config(txt)
    assert dict(filtered) == {'PEER_V6': ['ipv6'], 'PEER_V4': ['ipv4']}

def test_filter_bbr_config_disabled():
    template, kwargs = prepare_for_render("disabled")
    txt = template.render(**kwargs)
    filtered = filter_bbr_config(txt)
    assert dict(filtered) == {}

@patch("bgpcfgd.managers_bbr.log_warn")
def test_filter_bbr_config_wrong_order(patched_log):
    txt = """
  neighbor PEER_V6 allowas-in 1
address-family ipv6
    """
    filtered = filter_bbr_config(txt)
    assert dict(filtered) == {}
    patched_log.assert_called_with("BBR parser. no address family for 'PEER_V6' allowas-in")

def test_generate_config_good():
    tf = TemplateFabric()
    template = tf.from_string("{{ test }} - {{ CONFIG_DB__BGP_BBR['status'] }}")
    kwargs = {
        "test": "|test|",
        'CONFIG_DB__BGP_BBR': {
            "status": "123"
        }
    }
    assert generate_config(template, kwargs, "bbr") == "|test| - bbr"

@patch("bgpcfgd.managers_bbr.log_err")
def test_generate_config_exception(patched_log):
    tf = TemplateFabric()
    template = tf.from_string("{{ tes|int }}123")
    kwargs = {
        "te": "|test|",
        'CONFIG_DB__BGP_BBR': {
            "status": "123"
        }
    }
    assert generate_config(template, kwargs, "") == ""
    patched_log.assert_called_with("Can't render policy template to check bbr: 'tes' is undefined")

def test_compare_configs_changed():
    enabled = {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}
    disabled = {}
    res = compare_configs(enabled, disabled)
    assert res == {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}

def test_compare_configs_disabled_1():
    enabled = {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}
    disabled = {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}
    res = compare_configs(enabled, disabled)
    assert res == {}

def test_compare_configs_disabled_2():
    enabled = {}
    disabled = {}
    res = compare_configs(enabled, disabled)
    assert res == {}

def test_compare_configs_partially():
    enabled = {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}
    disabled = {"PEER_A": ["ipv4"]}
    res = compare_configs(enabled, disabled)
    assert res == {"PEER_B": ["ipv6"]}

def test_compare_configs_wrong_template():
    enabled = {"PEER_A": ["ipv4"]}
    disabled = {"PEER_A": ["ipv4"], "PEER_B": ["ipv6"]}
    res = compare_configs(enabled, disabled)
    assert res == {}

def directory_fabric(available_returns, initial_values):
    class Directory(object):
        def __init__(self):
            self.available_returns = available_returns
            self.values = initial_values
        def available(self, db, table):
            assert db == 'LOCAL'
            assert table == "BBR_peer-group"
            result = self.available_returns[0]
            self.available_returns = self.available_returns[1:]
            return result
        def get_slot(self, db, table):
            assert db == 'LOCAL'
            assert table == "BBR_peer-group"
            return self.values
        def put(self, db, table, key, value):
            assert db == 'LOCAL'
            assert table == "BBR_peer-group"
            self.values[key] = value
        def put_slot(self, db, table, slot_value):
            assert db == 'LOCAL'
            assert table == "BBR_peer-group"
            self.values = slot_value
        def get_values(self):
            return self.values
    return Directory()

def test_update_directory_not_available_empty():
    directory = directory_fabric([False], {})
    update_directory(directory, {"PG": ["ipv6"]})
    assert directory.get_values() == {"PG": ["ipv6"]}

def test_update_directory_available_empty():
    directory = directory_fabric([True], {})
    update_directory(directory, {"PG": ["ipv6"]})
    assert directory.get_values() == {"PG": ["ipv6"]}

def test_update_directory_available_not_empty():
    directory = directory_fabric([True], {"ZZ": ["ipv4"]})
    update_directory(directory, {"PG": ["ipv6"]})
    assert directory.get_values() == {"PG": ["ipv6"], "ZZ": ["ipv4"]}

def test_update_directory_available_not_empty_overwrite():
    directory = directory_fabric([True], {"P6": ["ipv4"]})
    update_directory(directory, {"P6": ["ipv6"]})
    assert directory.get_values() == {"P6": ["ipv6"]}

def test_extract_bbr_settings():
    directory = directory_fabric([True, True], {})
    template, kwargs = prepare_for_render("enabled")
    extract_bbr_settings(directory, template, kwargs)
    assert directory.get_values() == { "PEER_V6": ["ipv6"], "PEER_V4": ["ipv4"] }
