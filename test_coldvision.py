"""Tests for the SCHOTT ColdVision CV-LS driver."""

from unittest.mock import MagicMock, patch

import pytest

from coldvision import ColdVision, ColdVisionError


def _make_connected(mock_socket_cls, recv_replies):
    """Return a ColdVision connected to a mocked socket.
    """
    sock = mock_socket_cls.return_value
    sock.recv.side_effect = list(recv_replies)
    device = ColdVision(log=False)
    device.connect("127.0.0.1")
    return device, sock


@patch("coldvision.socket.socket")
def test_connect_and_disconnect(mock_socket_cls):
    sock = mock_socket_cls.return_value
    device = ColdVision(log=False)

    device.connect("127.0.0.1", port=50811)
    assert device.is_connected()
    sock.connect.assert_called_once_with(("127.0.0.1", 50811))

    device.disconnect()
    sock.close.assert_called_once()
    assert not device.is_connected()


@patch("coldvision.socket.socket")
def test_connect_failure_raises(mock_socket_cls):
    sock = mock_socket_cls.return_value
    sock.connect.side_effect = OSError("refused")
    device = ColdVision(log=False)

    with pytest.raises(ConnectionError):
        device.connect("127.0.0.1")
    assert not device.is_connected()
    sock.close.assert_called_once()


@patch("coldvision.socket.socket")
def test_get_product_name(mock_socket_cls):
    device, sock = _make_connected(
        mock_socket_cls, [b"&qSCHOTT ColdVision Light Source\r"]
    )
    assert device.get_product_name() == "SCHOTT ColdVision Light Source"
    sock.sendall.assert_called_once_with(b"&Q\r")


@patch("coldvision.socket.socket")
def test_get_firmware_revision_strips_query_mark(mock_socket_cls):
    device, sock = _make_connected(mock_socket_cls, [b"&f1.23\r"])
    assert device.get_firmware_revision() == "1.23"
    sock.sendall.assert_called_once_with(b"&F?\r")


@patch("coldvision.socket.socket")
def test_get_led_temperature(mock_socket_cls):
    device, _ = _make_connected(mock_socket_cls, [b"&?lt23.50\r"])
    assert device.get_led_temperature() == pytest.approx(23.50)


@patch("coldvision.socket.socket")
def test_get_and_set_power(mock_socket_cls):
    device, sock = _make_connected(mock_socket_cls, [b"&i0,500\r", b"&i0,750\r"])
    assert device.get_power() == 500
    sock.sendall.assert_called_with(b"&I0,?\r")

    assert device.set_power(750) == 750
    sock.sendall.assert_called_with(b"&I0,750\r")


def test_set_power_validates_range():
    device = ColdVision(log=False)
    with pytest.raises(ValueError):
        device.set_power(1001)


@patch("coldvision.socket.socket")
def test_get_and_set_enabled(mock_socket_cls):
    device, sock = _make_connected(mock_socket_cls, [b"&l1,0\r", b"&l1,1\r"])
    assert device.get_enabled(channel=1) is False
    sock.sendall.assert_called_with(b"&L1,?\r")

    assert device.set_enabled(True, channel=1) is True
    sock.sendall.assert_called_with(b"&L1,1\r")


@patch("coldvision.socket.socket")
def test_negative_acknowledgement_raises(mock_socket_cls):
    device, _ = _make_connected(mock_socket_cls, [b"&n1p1?\r"])
    with pytest.raises(ColdVisionError, match="Negative acknowledgement"):
        device.get_product_name()


@patch("coldvision.socket.socket")
def test_initialize_populates_identity(mock_socket_cls):
    device, _ = _make_connected(
        mock_socket_cls,
        [
            b"&qSCHOTT ColdVision Light Source\r",
            b"&zmCV-LS\r",
            b"&z123456\r",
            b"&f1.23\r",
        ],
    )
    assert device.initialize() is True
    assert device.is_initialized()
    assert device.product_name == "SCHOTT ColdVision Light Source"
    assert device.model == "CV-LS"
    assert device.serial_number == "123456"
    assert device.firmware_revision == "1.23"


@patch("coldvision.socket.socket")
def test_initialize_tolerates_unsupported_model_query(mock_socket_cls):
    device, _ = _make_connected(
        mock_socket_cls,
        [
            b"&qSCHOTT ColdVision Light Source\r",
            b"&nzM\r",
            b"&z123456\r",
            b"&f1.23\r",
        ],
    )
    assert device.initialize() is True
    assert device.model is None
    assert device.serial_number == "123456"
    assert device.firmware_revision == "1.23"


@patch("coldvision.socket.socket")
def test_initialize_fails_when_product_name_rejected(mock_socket_cls):
    device, _ = _make_connected(mock_socket_cls, [b"&nq\r"])
    assert device.initialize() is False
    assert not device.is_initialized()


def test_operations_require_connection():
    device = ColdVision(log=False)
    with pytest.raises(RuntimeError, match="not connected"):
        device.get_product_name()
