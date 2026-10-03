from unittest.mock import patch

import pytest

from app.core.config import get_settings


@pytest.mark.parametrize('transport,port', [('raw', 10011), ('ssh', 10022), (' SSH ', 10022)])
def test_query_transport_selects_default_port(transport, port):
    with patch.dict('os.environ', {'TS3_QUERY_TRANSPORT': transport}, clear=True):
        settings = get_settings()
    assert settings.ts3_query_transport == transport.strip().lower()
    assert settings.ts3_query_port == port


def test_existing_ts3_configuration_remains_raw():
    with patch.dict('os.environ', {'TS3_HOST': 'ts3.example', 'TS3_QUERY_PORT': '20011'}, clear=True):
        settings = get_settings()
    assert settings.ts3_query_transport == 'raw'
    assert settings.ts3_query_port == 20011
    assert settings.ts3_query_ssh_known_hosts == ''


def test_ssh_explicit_port_and_host_keys_are_preserved():
    with patch.dict('os.environ', {'TS3_QUERY_TRANSPORT': 'ssh', 'TS3_QUERY_PORT': '20022',
                                'TS3_QUERY_SSH_KNOWN_HOSTS': '/app/data/known_hosts'}, clear=True):
        settings = get_settings()
    assert settings.ts3_query_port == 20022
    assert settings.ts3_query_ssh_known_hosts == '/app/data/known_hosts'


@pytest.mark.parametrize('env', [{'TS3_QUERY_TRANSPORT': 'http'}, {'TS3_QUERY_PORT': '0'},
                               {'TS3_QUERY_PORT': '65536'}, {'TS3_QUERY_PORT': 'oops'}])
def test_invalid_query_configuration_fails_early(env):
    with patch.dict('os.environ', env, clear=True), pytest.raises(ValueError):
        get_settings()
