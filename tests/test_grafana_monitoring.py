import json
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[1]


def test_monitoring_network_and_host_isolation():
    compose=yaml.safe_load((ROOT/'docker-compose.yml').read_text(encoding='utf8'))
    for name in ('prometheus','node-exporter','airflow-monitor-init'):
        service=compose['services'][name]
        assert service['profiles']==['monitoring']
        assert 'ports' not in service
        assert not service.get('privileged',False)
    assert compose['networks']['monitoring']['internal'] is True
    node=compose['services']['node-exporter']
    assert node['pid']=='host' and node['volumes'][0]['read_only'] is True
    assert node['volumes'][0]['source']=='/'
    assert '--path.rootfs=/host' in node['command']
    assert 'monitoring' in compose['services']['grafana']['networks']
    assert 'airflow_control' in compose['services']['grafana']['networks']


def test_dashboards_datasources_and_sql_permissions():
    dashboards=ROOT/'grafana/provisioning/dashboards'
    for filename,uid in [('vps.json','vps-prometheus'),('airflow.json','airflow-monitoring')]:
        dashboard=json.loads((dashboards/filename).read_text(encoding='utf8'))
        assert dashboard['panels'] and dashboard['refresh']=='30s'
        for panel in dashboard['panels']:
            assert panel['datasource']['uid']==uid
    sql=(ROOT/'monitoring/airflow.sql').read_text(encoding='utf8')
    assert 'GRANT SELECT ON ALL TABLES IN SCHEMA monitoring' in sql
    assert 'GRANT SELECT ON ALL TABLES IN SCHEMA public' not in sql
    assert 'default_transaction_read_only=on' in sql
    assert 't.run_id' in sql  # Not all historical tasks accumulated together.


def test_retention_and_prometheus_scrapes():
    config=yaml.safe_load((ROOT/'monitoring/prometheus.yml').read_text())
    assert config['global']['scrape_interval']=='30s'
    assert config['scrape_configs'][0]['static_configs'][0]['targets']==['node-exporter:9100']
    rules=yaml.safe_load((ROOT/'monitoring/alerts.yml').read_text())
    assert len(rules['groups'][0]['rules'])==4
