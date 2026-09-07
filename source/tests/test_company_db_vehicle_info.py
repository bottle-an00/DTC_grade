from dtc_transform.company_db.vehicle_info import build_vehicle_info_index

VEHICLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<vehiclesdata>
  <geographiczone geozonecode="KOR">
    <manufacturer mfrcode="HY">
      <lang langcode="ENG">
        <vehicletype vehicletypevincode="8">
          <model modeldesc="ACCENT(HC)">
            <modelvin modelvincode="C" modelcode="HC13">
              <modelyr modelyr="2022">
                <engine enginecode="157">
                  <sysitem sysitemtype="en" sysitemdesc="ENGINE">
                    <syssubitem syssubitemcode="157" syssubitemdesc="Engine Control">
                      <ecuid ecucode="E0A1" />
                    </syssubitem>
                  </sysitem>
                  <sysitem sysitemtype="ab" sysitemdesc="AIRBAG">
                    <syssubitem syssubitemcode="36" syssubitemdesc="Airbag">
                      <ecuid ecucode="D2O6" />
                    </syssubitem>
                  </sysitem>
                </engine>
              </modelyr>
            </modelvin>
          </model>
        </vehicletype>
      </lang>
    </manufacturer>
  </geographiczone>
</vehiclesdata>
"""

CONFLICTING_XML = """<?xml version="1.0" encoding="utf-8"?>
<vehiclesdata>
  <geographiczone geozonecode="USA">
    <manufacturer mfrcode="HY">
      <lang langcode="ENG">
        <vehicletype vehicletypevincode="8">
          <model modeldesc="OTHER(XX)">
            <modelvin modelvincode="X" modelcode="XX99">
              <modelyr modelyr="2023">
                <engine enginecode="1">
                  <sysitem sysitemtype="xx" sysitemdesc="SOMETHING_ELSE">
                    <syssubitem syssubitemcode="1" syssubitemdesc="Other">
                      <ecuid ecucode="E0A1" />
                    </syssubitem>
                  </sysitem>
                </engine>
              </modelyr>
            </modelvin>
          </model>
        </vehicletype>
      </lang>
    </manufacturer>
  </geographiczone>
</vehiclesdata>
"""


def test_builds_ecucode_to_sysitemdesc_index(tmp_path):
    path = tmp_path / "vehiclesdata_HMA.xml"
    path.write_text(VEHICLE_XML, encoding="utf-8")

    resolved, conflicts = build_vehicle_info_index([str(path)])

    assert resolved == {"E0A1": "ENGINE", "D2O6": "AIRBAG"}
    assert conflicts == {}


def test_same_ecucode_with_different_sysitemdesc_across_files_is_a_conflict(tmp_path):
    path_a = tmp_path / "vehiclesdata_HMA.xml"
    path_a.write_text(VEHICLE_XML, encoding="utf-8")
    path_b = tmp_path / "vehiclesdata_KMC.xml"
    path_b.write_text(CONFLICTING_XML, encoding="utf-8")

    resolved, conflicts = build_vehicle_info_index([str(path_a), str(path_b)])

    assert "E0A1" not in resolved
    assert conflicts["E0A1"] == {"ENGINE", "SOMETHING_ELSE"}
    assert resolved["D2O6"] == "AIRBAG"
