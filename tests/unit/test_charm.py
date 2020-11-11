#!/usr/bin/env python3

import copy
import mock
import unittest

from charm import WordpressCharm, create_wordpress_secrets, gather_wordpress_secrets
from wordpress import WORDPRESS_SECRETS
from ops import testing
from ops.model import BlockedStatus

from test_wordpress import TEST_MODEL_CONFIG


class TestLeadershipData:
    data = {}

    def _leader_set(self, d):
        self.data.update(d)

    def _leader_get(self, k):
        return self.data.get(k)


class TestWordpressCharm(unittest.TestCase):

    test_model_config = TEST_MODEL_CONFIG

    def setUp(self):
        self.harness = testing.Harness(WordpressCharm)

        self.harness.begin()
        self.harness.update_config(copy.deepcopy(self.test_model_config))

    def test_is_config_valid(self):
        # Test a valid model config.
        want_true = self.harness.charm.is_valid_config()
        self.assertTrue(want_true)

        # Test for invalid model config.
        want_msg_fmt = "Missing required config: {}"
        want_keys = ("image", "db_host", "db_name", "db_user", "db_password", "tls_secret_name")
        for wanted_key in want_keys:
            self.harness.update_config({wanted_key: ""})
            want_false = self.harness.charm.is_valid_config()
            self.assertFalse(want_false)
            self.assertLogs(want_msg_fmt.format(wanted_key), level="INFO")
            self.harness.update_config(copy.deepcopy(self.test_model_config))

        # Test for missing initial_settings in model config.
        self.harness.update_config({"initial_settings": ""})
        want_false = self.harness.charm.is_valid_config()
        self.assertFalse(want_false)
        self.assertLogs("No initial_setting provided. Skipping first install.", level="INFO")
        self.harness.update_config(copy.deepcopy(self.test_model_config))

        # Test unit status msg.
        for wanted_key in want_keys:
            self.harness.update_config({wanted_key: ""})
        expected_msg = want_msg_fmt.format(" ".join(want_keys))
        self.harness.charm.is_valid_config()
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)
        self.assertEqual(self.harness.charm.unit.status.message, expected_msg)
        self.assertLogs(expected_msg, level="INFO")

    @mock.patch("charm._leader_set")
    @mock.patch("charm._leader_get")
    def test_create_wordpress_secrets(self, _leader_get_func, _leader_set_func):
        leadership_data = TestLeadershipData()
        _leader_set_func.side_effect = leadership_data._leader_set
        _leader_get_func.side_effect = leadership_data._leader_get
        create_wordpress_secrets()

        self.assertEqual(sorted(list(leadership_data.data.keys())), sorted(WORDPRESS_SECRETS))

    @mock.patch("charm._leader_set")
    @mock.patch("charm._leader_get")
    def test_gather_wordpress_secrets(self, _leader_get_func, _leader_set_func):
        leadership_data = TestLeadershipData()
        _leader_set_func.side_effect = leadership_data._leader_set
        _leader_get_func.side_effect = leadership_data._leader_get
        create_wordpress_secrets()
        wp_secrets = gather_wordpress_secrets()
        for key in WORDPRESS_SECRETS:
            self.assertIsInstance(wp_secrets[key], str)
            self.assertEqual(len(wp_secrets[key]), 64)

    def test_make_pod_resources(self):
        self.harness.update_config({
            "blog_hostname": "blog.example.com",
            "tls_secret_name": "blog-example-com-tls"
        })
        # Test for https://bugs.launchpad.net/juju/+bug/1884674
        ingress_name = 'wordpress-ingress'
        self.assertNotEqual(ingress_name, self.harness.charm.app.name)

        expected = {
            'kubernetesResources': {
                'ingressResources': [
                    {
                        "annotations": {
                            "nginx.ingress.kubernetes.io/proxy-body-size": "10m",
                            "nginx.ingress.kubernetes.io/proxy-send-timeout": "300s",
                        },
                        'name': ingress_name,
                        'spec': {
                            'rules': [
                                {
                                    'host': 'blog.example.com',
                                    'http': {
                                        'paths': [
                                            {
                                                'path': '/',
                                                'backend': {'serviceName': 'wordpress', 'servicePort': 80},
                                            }
                                        ]
                                    },
                                }
                            ],
                            'tls': [{'hosts': ['blog.example.com'], 'secretName': 'blog-example-com-tls'}],
                        },
                    }
                ]
            }
        }
        self.assertEqual(self.harness.charm.make_pod_resources(), expected)
