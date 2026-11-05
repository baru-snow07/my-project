"""Run a SQL statement on the Databricks SQL warehouse through the CLI and print the result as a table.

    python databricks/tools/sql.py "SELECT 1"
Uses the CLI profile `cyber` (signed in with `databricks auth login`) and warehouse `cyber-dashboard`.
"""
import json, os, shutil, subprocess, sys, time

CLI = shutil.which('databricks') or os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links\databricks.exe')
PROFILE, WAREHOUSE = 'cyber', os.environ.get('CYBER_WAREHOUSE_ID', '329344431e53eb52')
CATALOG, SCHEMA = os.environ.get('CYBER_CATALOG', 'databricks_demo_ws'), os.environ.get('CYBER_SCHEMA', 'cyber')


def api(method, path, body=None):
    cmd = [CLI, 'api', method, path, '-p', PROFILE] + (['--json', json.dumps(body)] if body else [])
    out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if out.returncode:
        sys.exit(out.stderr)
    return json.loads(out.stdout)


def run(sql, timeout_s=600):
    res = api('post', '/api/2.0/sql/statements', {'warehouse_id': WAREHOUSE, 'statement': sql, 'wait_timeout': '50s',
                                                  'catalog': CATALOG, 'schema': SCHEMA})
    # A cold warehouse or a heavy query outlasts the 50 s wait: keep polling instead of giving up.
    deadline = time.time() + timeout_s
    while res['status']['state'] in ('PENDING', 'RUNNING') and time.time() < deadline:
        time.sleep(3)
        res = api('get', f"/api/2.0/sql/statements/{res['statement_id']}")
    if res['status']['state'] != 'SUCCEEDED':
        sys.exit(json.dumps(res['status'], indent=1))
    cols = [c['name'] for c in res['manifest']['schema']['columns']]
    return cols, res.get('result', {}).get('data_array', [])


if __name__ == '__main__':
    cols, rows = run(sys.argv[1])
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    print(' | '.join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print(' | '.join(str(v).ljust(w) for v, w in zip(r, widths)))
