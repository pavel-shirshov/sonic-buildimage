from unittest import TestCase
import subprocess
import os

class TestCfgGenCaseInsensitive(TestCase):

    def setUp(self):
        self.test_dir = os.path.dirname(os.path.realpath(__file__))
        self.script_file = os.path.join(self.test_dir, '..', 'sonic-cfggen')
        self.sample_graph = os.path.join(self.test_dir, 'input/simple-sample-graph-case.xml')
        self.port_config = os.path.join(self.test_dir, 'input/ini/ini_aliases.ini')

    def run_script(self, argument, check_stderr=False):
        print '\n    Running sonic-cfggen ' + argument
        if check_stderr:
            output = subprocess.check_output(self.script_file + ' ' + argument, stderr=subprocess.STDOUT, shell=True)
        else:
            output = subprocess.check_output(self.script_file + ' ' + argument, shell=True)

        output = output.strip()
        linecount = output.count('\n')
        if linecount <= 0:
            print '    Empty output  '
        else:
            print '    Output: ({0} lines, {1} bytes)'.format(linecount + 1, len(output))
        return output

    def run_case_str(self, argument, expected):
        output = self.run_script(argument)
        self.assertEqual(output, expected)

    def run_case_dict(self, argument, expected):
        output = self.run_script(argument)
        j1 = json.loads(output)
        j2 = json.loads(expected)
        self.assertDictEqual(j1, j2)

    def test_dummy_run(self):
        self.run_case_str('', '')

    def test_minigraph_sku(self):
        self.run_case_str('-v "DEVICE_METADATA[\'localhost\'][\'hwsku\']" -m "' + self.sample_graph + '"', 'Force10-S6000')

    def test_print_data(self):
        argument = '-m "' + self.sample_graph + '" --print-data'
        output = self.run_script(argument)
        self.assertGreater(len(output), 0)

    def test_jinja_expression(self):
        self.run_case_str('-m "' + self.sample_graph + '" -v "DEVICE_METADATA[\'localhost\'][\'type\']"', 'ToRRouter')

    def test_additional_json_data(self):
        self.run_case_str('-a \'{"key1":"value1"}\' -v key1', 'value1')

    def test_read_yaml(self):
        self.run_case_str('-v yml_item -y ' + os.path.join(self.test_dir, 'test.yml'), '[\'value1\', \'value2\']')

    def test_render_template(self):
        self.run_case_str('-y ' + os.path.join(self.test_dir, 'test.yml') + ' -t ' + os.path.join(self.test_dir, 'test.j2'), 'value1\nvalue2')

#     everflow portion is not used
#     def test_minigraph_everflow(self):
#         argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v MIRROR_SESSION'
#         output = self.run_script(argument)
#         self.assertEqual(output.strip(), "{'everflow0': {'src_ip': '10.1.0.32', 'dst_ip': '10.0.100.1'}}")

    def test_minigraph_interfaces(self):
        self.run_case_str('-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v \'INTERFACE.keys()\'',
            "[('Ethernet0', '10.0.0.58/31'), 'Ethernet0', ('Ethernet0', 'FC00::75/126')]") # the order could be any here

    def test_minigraph_vlans(self):
        self.run_case_dict('-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v VLAN',
            "{'Vlan1000': {'alias': 'ab1', 'dhcp_servers': ['192.0.0.1', '192.0.0.2'], 'vlanid': '1000'}}")

    def test_minigraph_vlan_members(self):
        self.run_case_dict('-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v VLAN_MEMBER',
            "{('Vlan1000', 'Ethernet8'): {'tagging_mode': 'untagged'}}")

    def test_minigraph_vlan_interfaces(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "VLAN_INTERFACE.keys()"'
        output = self.run_script(argument)
        self.assertEqual(output, "[('Vlan1000', '192.168.0.1/27'), 'Vlan1000']")

    def test_minigraph_portchannels(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v PORTCHANNEL'
        output = self.run_script(argument)
        self.assertEqual(output, "{'PortChannel01': {'admin_status': 'up', 'min_links': '1', 'members': ['Ethernet4'], 'mtu': '9100'}}")

    def test_minigraph_console_port(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v CONSOLE_PORT'
        output = self.run_script(argument)
        self.assertEqual(output, "{'1': {'baud_rate': '9600', 'remote_device': 'managed_device', 'flow_control': 1}}")

    def test_minigraph_deployment_id(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "DEVICE_METADATA[\'localhost\'][\'deployment_id\']"'
        output = self.run_script(argument)
        self.assertEqual(output, "1")

    def test_minigraph_neighbor_metadata(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "DEVICE_NEIGHBOR_METADATA"'
        output = self.run_script(argument)
        self.assertEqual(output, "{'switch-01t1': {'lo_addr': '10.1.0.186/32', 'mgmt_addr': '10.7.0.196/26', 'hwsku': 'Force10-S6000', 'type': 'LeafRouter', 'deployment_id': '2'}}")

#     everflow portion is not used
#     def test_metadata_everflow(self):
#         argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "MIRROR_SESSION"'
#         output = self.run_script(argument)
#         self.assertEqual(output.strip(), "{'everflow0': {'src_ip': '10.1.0.32', 'dst_ip': '10.0.100.1'}}")

    def test_metadata_tacacs(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "TACPLUS_SERVER"'
        output = self.run_script(argument)
        self.assertEqual(output, "{'10.0.10.7': {'priority': '1', 'tcp_port': '49'}, '10.0.10.8': {'priority': '1', 'tcp_port': '49'}}")

    def test_minigraph_mgmt_port(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "MGMT_PORT"'
        output = self.run_script(argument)
        self.assertEqual(output, "{'eth0': {'alias': 'eth0', 'admin_status': 'up', 'speed': '1000'}}")

    def test_metadata_ntp(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "NTP_SERVER"'
        output = self.run_script(argument)
        self.assertEqual(output, "{'10.0.10.1': {}, '10.0.10.2': {}}")

    def test_minigraph_vnet(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "VNET"'
        output = self.run_script(argument)
        self.assertEqual(output, "")

    def test_minigraph_vxlan(self):
        argument = '-m "' + self.sample_graph + '" -p "' + self.port_config + '" -v "VXLAN_TUNNEL"'
        output = self.run_script(argument)
        self.assertEqual(output, "")
