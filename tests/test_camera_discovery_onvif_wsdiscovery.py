import xml.etree.ElementTree as ET

from app.utils.camera_discovery import (
    _looks_like_onvif_ws_discovery,
    _xml_text_by_localname,
)


def test_xml_text_by_localname_handles_namespaces():
    xml = ET.fromstring(
        b"""<e:Envelope xmlns:e='http://www.w3.org/2003/05/soap-envelope'
        xmlns:d='http://schemas.xmlsoap.org/ws/2005/04/discovery'>
        <e:Body>
          <d:ProbeMatches>
            <d:ProbeMatch>
              <d:Types>dn:NetworkVideoTransmitter</d:Types>
              <d:Scopes>onvif://www.onvif.org/Profile/Streaming</d:Scopes>
              <d:XAddrs>http://192.168.1.10/onvif/device_service</d:XAddrs>
            </d:ProbeMatch>
          </d:ProbeMatches>
        </e:Body>
      </e:Envelope>"""
    )
    assert _xml_text_by_localname(xml, "Types") == "dn:NetworkVideoTransmitter"
    assert "onvif" in (_xml_text_by_localname(xml, "Scopes") or "").lower()
    assert (
        _xml_text_by_localname(xml, "XAddrs")
        == "http://192.168.1.10/onvif/device_service"
    )


def test_looks_like_onvif_ws_discovery_true_for_onvif_types():
    assert (
        _looks_like_onvif_ws_discovery({"types": "dn:NetworkVideoTransmitter"}) is True
    )


def test_looks_like_onvif_ws_discovery_true_for_onvif_scopes():
    assert (
        _looks_like_onvif_ws_discovery(
            {"scopes": "onvif://www.onvif.org/Profile/Streaming"}
        )
        is True
    )


def test_looks_like_onvif_ws_discovery_true_for_onvif_xaddr():
    assert (
        _looks_like_onvif_ws_discovery(
            {"xaddr": "http://192.168.1.10/onvif/device_service"}
        )
        is True
    )


def test_looks_like_onvif_ws_discovery_false_for_router_login_page():
    assert (
        _looks_like_onvif_ws_discovery(
            {
                "xaddr": "http://192.168.2.7/Main_Login.asp",
                "types": "",
                "scopes": "",
            }
        )
        is False
    )
