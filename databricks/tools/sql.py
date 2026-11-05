"""Run a SQL statement on the Databricks SQL warehouse through the CLI and print the result as a table.

    python databricks/tools/sql.py "SELECT 1"
Uses the CLI profile `cyber` (signed in with `databricks auth login`) and warehouse `cyber-dashboard`.
"""
import json, os, subprocess, sys

CLI = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links\databricks.exe')
PROFILE, WAREHOUSE = 'cyber', os.environ.get('CYBER_WAREHOUSE_ID', '329344431e53eb52')


def run(sql):
    body = json.dumps({'warehouse_id': WAREHOUSE, 'statement': sql, 'wait_timeout': '50s',
                       'catalog': 'databricks_demo_ws', 'schema': 'cyber'})
    out = subprocess.run([CLI, 'api', 'post', '/api/2.0/sql/statements', '--json', body, '-p', PROFILE],
                         capture_output=True, text=True, encoding='utf-8')
    if out.returncode:
        sys.exit(out.stderr)
    res = json.loads(out.stdout)
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
