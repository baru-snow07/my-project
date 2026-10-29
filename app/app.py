"""Sales app: find, filter and prioritise companies that need cybersecurity help.

    streamlit run app/app.py
"""
import os
import pandas as pd
import streamlit as st

DATA = os.path.join(os.path.dirname(__file__), 'data', 'companies.parquet')
TIERS = ['Breached / data exposed', 'Actively exploited CVE', 'Exposed critical service',
         'Vulnerable software', 'Poor hygiene', 'Low signal']

# Score column -> how a salesperson would say it. {n} is filled with the matching count.
REASONS = {
    's_compromised': ('Already compromised: a service is tagged as breached (e.g. ransom note in a database)', None),
    's_unauth_data': ('Data open to anyone: a database or search index answers without a password', None),
    's_anon_ftp': ('Allows anonymous FTP logins', None),
    's_kev': ('Runs software with {n} CVE(s) on the US government\'s Known Exploited list', 'kev_cves'),
    's_ransomware': ('Has CVEs used by known ransomware gangs', None),
    's_high_epss': ('{n} server(s) with flaws likely to be exploited in the next 30 days (EPSS ≥ 10%)', 'hosts_high_epss'),
    's_remote': ('{n} server(s) expose remote access (RDP / SMB / Telnet / VNC) to the internet', 'hosts_remote_access'),
    's_database': ('{n} database server(s) reachable from the internet', 'hosts_database'),
    's_industrial': ('{n} industrial control system(s) exposed', 'hosts_industrial'),
    's_open_dir': ('A web server lists its files publicly', None),
    's_ntlm': ('A Windows service leaks internal domain / machine names', None),
    's_eol': ('{n} server(s) run end-of-life software that no longer gets security fixes', 'hosts_eol'),
    's_cert': ('Website certificate has expired', None),
    's_legacy_tls': ('Still accepts outdated encryption (SSLv3 / TLS 1.0 / 1.1)', None),
    's_self_signed': ('Uses self-signed certificates', None),
    's_no_hsts': ('Website does not enforce HTTPS (no HSTS)', None),
    's_waf': ('Already behind a web application firewall', None),
    's_security_txt': ('Publishes a security contact (likely has a security team)', None),
    's_pqc': ('Uses post-quantum TLS (modern, well-run stack)', None),
}


def sector(domain):
    d = domain.lower()
    if any(t in d for t in ('.edu', '.ac.', 'univ', 'school', 'college')): return 'Education'
    if any(t in d for t in ('.gov', '.gob.', '.go.', '.mil')): return 'Government'
    if any(t in d for t in ('health', 'hospital', 'clinic', 'medic', 'pharma', 'dental')): return 'Healthcare'
    if any(t in d for t in ('bank', 'finance', 'capital', 'insur', 'invest', 'credit')): return 'Finance'
    if d.endswith('.org') or '.or.' in d: return 'Non-profit'
    return 'Business'


@st.cache_data
def load():
    df = pd.read_parquet(DATA)
    df['sector'] = df['company'].map(sector)
    return df


def reasons(row):
    out = []
    for col, (text, count_col) in REASONS.items():
        pts = int(row.get(col) or 0)
        if pts:
            out.append((pts, text.format(n=int(row[count_col])) if count_col else text))
    return sorted(out, key=lambda x: -x[0])


st.set_page_config(page_title='Cyber Prospecting', page_icon='🛡️', layout='wide')
st.title('🛡️ Cyber Prospecting')
st.caption('Companies ranked by how urgently their internet-facing systems need security help, from one internet scan snapshot.')

if not os.path.exists(DATA):
    st.error('No data yet. Run `python pipeline/ingest.py <file>` and `python pipeline/build.py` first.')
    st.stop()
df = load()

with st.sidebar:
    st.header('Filter accounts')
    q = st.text_input('Search domain')
    tiers = st.multiselect('Why now', TIERS, default=TIERS[:4])
    sectors = st.multiselect('Sector', sorted(df['sector'].unique()))
    countries = st.multiselect('Country', df['country'].value_counts().index.tolist())
    min_ips = st.slider('Minimum internet-facing IPs (company size proxy)', 1, 50, 1)
    hide_cdn = st.checkbox('Hide companies only seen behind a CDN', value=False)

f = df[df['tier'].isin(tiers)] if tiers else df
if q: f = f[f['company'].str.contains(q.lower(), regex=False)]
if sectors: f = f[f['sector'].isin(sectors)]
if countries: f = f[f['country'].isin(countries)]
f = f[f['ips'] >= min_ips]
if hide_cdn: f = f[~f['cdn_only']]

c = st.columns(4)
c[0].metric('Accounts', f'{len(f):,}')
c[1].metric('Breached / data exposed', f'{(f.tier == TIERS[0]).sum():,}')
c[2].metric('Actively exploited CVE', f'{(f.tier == TIERS[1]).sum():,}')
c[3].metric('Exposed critical service', f'{(f.tier == TIERS[2]).sum():,}')

view = f.head(500).copy()
# A list (not DataFrame.apply) so an empty filter result gives an empty column instead of crashing.
view['top reason'] = [(reasons(r) or [(0, '')])[0][1] for _, r in view.iterrows()]
picked = st.dataframe(
    view[['company', 'risk_score', 'tier', 'sector', 'country', 'ips', 'top reason']],
    column_config={'risk_score': st.column_config.ProgressColumn('score', min_value=0, max_value=int(df.risk_score.max()), format='%d'),
                   'ips': 'IPs'},
    hide_index=True, width='stretch', on_select='rerun', selection_mode='single-row', height=420)

rows = picked.selection.rows
if not rows:
    st.info('Select a company to see why it ranks here and what to say on the first call.')
    st.stop()
r = view.iloc[rows[0]]

st.divider()
left, right = st.columns([3, 2])
with left:
    st.subheader(r['company'])
    st.write(f"**{r['tier']}** · score **{int(r['risk_score'])}** · {r['sector']} · {r['city'] or ''} {r['country'] or ''} · {int(r['ips'])} IPs on {r['network_org']}")
    if r['web_title']: st.write(f"Website: *{r['web_title']}*")
    st.markdown('**Why this account, why now**')
    for pts, text in reasons(r):
        st.write(f"{'🔴' if pts >= 20 else '🟠' if pts >= 8 else '🟢' if pts < 0 else '🟡'} {text}  `{pts:+d}`")
    top = reasons(r)
    if top and top[0][0] > 0:
        st.markdown('**Opening line**')
        st.info(f"Public internet scan data shows this about {r['company']}: {top[0][1][0].lower() + top[0][1][1:]}. "
                f"That's one of the first things attackers scan for. Could we show you what else is visible from outside?")
with right:
    cves = list(dict.fromkeys([*r['kev_list'], *r['top_cves']]))[:6]
    if cves:
        st.markdown('**Most dangerous CVEs**')
        for cve in cves:
            st.write(f"[{cve}](https://nvd.nist.gov/vuln/detail/{cve})" + ('  · known exploited' if cve in r['kev_list'] else ''))
    if len(r['exposed_services']):
        st.markdown('**Exposed services**')
        st.write(', '.join(r['exposed_services']))
    if len(r['tech']):
        st.markdown('**Tech stack seen**')
        st.write(', '.join(r['tech']))
    st.caption(f"Last seen {str(r['last_seen'])[:10]}")
