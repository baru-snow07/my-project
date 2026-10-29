"""Sales app: find, filter and prioritise companies that need cybersecurity help.

    streamlit run app/app.py
"""
import json, os
import pandas as pd
import streamlit as st

HERE = os.path.join(os.path.dirname(__file__), 'data')
DATA = os.path.join(HERE, 'companies.parquet')
TIERS = ['Breached / data exposed', 'Actively exploited CVE', 'Exposed critical service',
         'Vulnerable software', 'Poor hygiene']

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

TRAPS = pd.DataFrame([
    ['"Malware" fields', 'The scanner field names the probe it *tried* (e.g. `orcus-rat`), not what it found. Most got an error back.',
     'Only count a service when its protocol actually answered'],
    ['CDN / cloud edges', 'About half the records are Cloudflare / Incapsula / Google servers that answer on every port.',
     'Port and CVE signals never count on CDN edges'],
    ['ISP reverse DNS', 'Names like `ip-51-79-39.net` look like companies but belong to providers.',
     'Ownership check: do the certificates / websites on those hosts name the domain?'],
    ['Guessed CVEs', 'CVEs are matched from version numbers; one (HTTP/2 Rapid Reset) is on almost every nginx server.',
     'Weight by exploit likelihood (EPSS) and down-weight CVEs found on 5%+ of hosts'],
    ['Honeypots', 'Decoy servers that pretend to be vulnerable.', 'Dropped'],
], columns=['Trap', 'What it looks like', 'What the pipeline does']).set_index('Trap')


def sector(domain):
    d = domain.lower()
    if any(t in d for t in ('.edu', '.ac.', 'univ', 'school', 'college')): return 'Education'
    if any(t in d for t in ('.gov', '.gob.', '.go.', '.mil')): return 'Government'
    if any(t in d for t in ('health', 'hospital', 'clinic', 'medic', 'pharma', 'dental')): return 'Healthcare'
    if any(t in d for t in ('bank', 'finance', 'capital', 'insur', 'invest', 'credit')): return 'Finance'
    if d.endswith('.org') or '.or.' in d: return 'Non-profit'
    return 'Business'


COUNTS = ['kev_cves', 'hosts_high_epss', 'hosts_remote_access', 'hosts_database', 'hosts_industrial', 'hosts_eol']
COLUMNS = ['company', 'risk_score', 'tier', 'country', 'city', 'ips', 'network_org', 'web_title', 'cdn_only', 'last_seen',
           'kev_list', 'top_cves', 'exposed_services', 'tech', *COUNTS, *REASONS]


# cache_resource keeps one shared copy (cache_data would copy the frame on every rerun, which
# overflows the 1 GB Streamlit Cloud limit); the app never mutates these frames.
@st.cache_resource
def load():
    # "Low signal" accounts (only minor hygiene issues) are not worth a sales call; skipping them
    # halves memory.
    df = pd.read_parquet(DATA, columns=COLUMNS, filters=[('tier', '!=', 'Low signal')])
    df['sector'] = df['company'].map(sector).astype('category')
    for col in ('tier', 'country', 'network_org'):
        df[col] = df[col].astype('category')
    return df


@st.cache_resource
def load_extras():
    ev = pd.read_parquet(os.path.join(HERE, 'evidence.parquet'))
    with open(os.path.join(HERE, 'stats.json')) as f:
        stats = json.load(f)
    path = os.path.join(HERE, 'eval.json')
    evaluation = json.load(open(path)) if os.path.exists(path) else None
    return ev, stats, evaluation


def reasons(row):
    out = []
    for col, (text, count_col) in REASONS.items():
        pts = int(row.get(col) or 0)
        if pts:
            out.append((pts, text.format(n=int(row[count_col])) if count_col else text))
    return sorted(out, key=lambda x: -x[0])


def how_it_works(stats, evaluation):
    st.subheader('1. The data')
    st.write('One file of internet-scan results (Shodan format, 17.6 GB compressed). Each of its **14.6 million '
             'records is one service on one IP and port**: what software answered, its version, TLS certificate, '
             'HTTP headers, known CVEs, location and network owner. Companies are not given; they have to be inferred.')

    st.subheader('2. Pipeline')
    c = st.columns(4)
    c[0].metric('Scan records', '14.6M')
    c[1].metric('Rows tied to a company', f"{stats['rows']:,}")
    c[2].metric('Companies identified', f"{stats['domain_companies']:,}")
    c[3].metric('Companies with a risk signal', f"{stats['scored']:,}")
    st.markdown(
        '1. **Stream** the compressed file record by record (never unzipped) across all CPU cores: ~25k records/s.\n'
        '2. **Attribute** each record to a company domain, then remove infrastructure with rules learned from the data: '
        f"**{stats['providers']:,}** network providers and **{stats['infra_domains']:,}** ISP / hosting / dynamic-DNS domains.\n"
        '3. **Score** each company on the signals below with DuckDB SQL (~12 s for all companies).\n'
        '4. New files are added the same way, so the pipeline keeps up with hundreds of files a month.')

    st.subheader("3. Traps in the data (why it can't just be handed to an AI)")
    st.table(TRAPS)

    st.subheader('4. Scoring')
    st.write('Each signal adds or removes points. Every company keeps its breakdown, so any score can be explained line by line.')
    weights = pd.DataFrame(sorted(stats['weights'].items(), key=lambda x: -x[1]), columns=['signal', 'points'])
    st.dataframe(weights, hide_index=True, width='content')
    st.write('**Tier** = the single strongest reason (breached → exploited CVE → exposed service → vulnerable software → '
             'poor hygiene). That is the "why now" a salesperson filters on.')

    if evaluation:
        st.subheader('5. Does it work? Back-test against real breaches')
        st.write(f"The data contains **{evaluation['breached_hosts']} servers that were already breached** (tagged compromised, "
                 'or a database open to anyone). Every server was scored **without** those breach signals, to see if the '
                 'warning signs alone point to them.')
        c = st.columns(2)
        c[0].metric('AUC (0.5 = random, 1.0 = perfect)', f"{evaluation['auc']:.2f}")
        c[1].metric('Breached servers in the top 10,000', f"{evaluation['top10k_lift']}× the average rate")
        lift = pd.DataFrame(evaluation['lift']).set_index('signal')['lift']
        st.write('How much more often servers with each signal were breached (1.0 = no effect):')
        st.bar_chart(lift[lift > 0], horizontal=True)
        st.caption(f"Only {evaluation['breached_hosts']} labelled breaches, so per-signal values are directional. "
                   'End-of-life software is the strongest single predictor.')

    st.subheader('6. Responsible use')
    st.write('IP addresses are partly masked (e.g. `128.32.x.x`) so this public page is not a target list. '
             'All data comes from public internet scans; no system was accessed.')


def accounts(df, evidence, common_kev):
    with st.sidebar:
        st.header('Filter accounts')
        q = st.text_input('Search domain', placeholder='e.g. berkeley.edu')
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

    st.info('**How to use:** filter on the left → tick a company in the table → read why it ranks there, '
            'the servers behind it, and a suggested opening line. The **How it works** tab explains the method.')
    c = st.columns(4)
    c[0].metric('Accounts', f'{len(f):,}')
    c[1].metric('Breached / data exposed', f'{(f.tier == TIERS[0]).sum():,}')
    c[2].metric('Actively exploited CVE', f'{(f.tier == TIERS[1]).sum():,}')
    c[3].metric('Exposed critical service', f'{(f.tier == TIERS[2]).sum():,}')

    view = f.head(500).copy()
    view['top reason'] = view.apply(lambda r: (reasons(r) or [(0, '')])[0][1], axis=1)
    export = view[['company', 'risk_score', 'tier', 'sector', 'country', 'city', 'ips', 'network_org', 'top reason']]
    st.download_button('⬇️ Export these accounts (CSV)', export.to_csv(index=False), 'accounts.csv', 'text/csv')
    picked = st.dataframe(
        view[['company', 'risk_score', 'tier', 'sector', 'country', 'ips', 'top reason']],
        column_config={'risk_score': st.column_config.ProgressColumn('score', min_value=0, max_value=int(df.risk_score.max()), format='%d'),
                       'ips': 'IPs'},
        hide_index=True, width='stretch', on_select='rerun', selection_mode='single-row', height=420)

    rows = picked.selection.rows
    if not rows:
        st.caption('👆 Tick a company to see the details.')
        return
    r = view.iloc[rows[0]]

    st.divider()
    st.subheader(r['company'])
    st.write(f"**{r['tier']}** · score **{int(r['risk_score'])}** · {r['sector']} · {r['city'] or ''} {r['country'] or ''} · "
             f"{int(r['ips'])} internet-facing IPs, mainly on {r['network_org']}")
    if r['web_title']: st.write(f"Website title: *{r['web_title']}*")

    left, right = st.columns([3, 2])
    with left:
        st.markdown('**Why this account, why now**')
        top = reasons(r)
        for pts, text in top:
            st.write(f"{'🔴' if pts >= 20 else '🟠' if pts >= 8 else '🟢' if pts < 0 else '🟡'} {text}  `{pts:+d}`")
        st.caption(f"Score = {' + '.join(str(p) for p, _ in top).replace('+ -', '- ')} = {int(r['risk_score'])}")
        if top and top[0][0] > 0:
            st.markdown('**Opening line for the first call**')
            st.info(f"Public internet scan data shows this about {r['company']}: {top[0][1][0].lower() + top[0][1][1:]}. "
                    "That's one of the first things attackers scan for. Could we show you what else is visible from outside?")
    with right:
        cves = list(dict.fromkeys([*r['kev_list'], *r['top_cves']]))[:6]
        if cves:
            st.markdown('**Most dangerous CVEs**')
            for cve in cves:
                tag = ('  · known exploited, but on 5%+ of hosts (often a version-number false match)' if cve in common_kev
                       else '  · **known exploited**' if cve in r['kev_list'] else '')
                st.write(f"[{cve}](https://nvd.nist.gov/vuln/detail/{cve}){tag}")
        if len(r['exposed_services']):
            st.markdown('**Exposed services**')
            st.write(', '.join(r['exposed_services']))
        if len(r['tech']):
            st.markdown('**Tech stack seen**')
            st.write(', '.join(r['tech']))

    ev = evidence[evidence['company'] == r['company']].sort_values('rank')
    if len(ev):
        st.markdown('**Evidence: the servers behind this score** (worst first, IPs masked)')
        ev = ev.assign(issues=ev['issues'].map(lambda xs: ' · '.join(xs)))
        st.dataframe(ev[['ip', 'port', 'software', 'issues']], hide_index=True, width='stretch')
    st.caption(f"Scan date {str(r['last_seen'])[:10]}. Every line above comes from a field in the scan record.")


st.set_page_config(page_title='Cyber Prospecting', page_icon='🛡️', layout='wide')
st.title('🛡️ Cyber Prospecting')
st.caption('Companies ranked by how urgently their internet-facing systems need security help, '
           'built from one internet-scan snapshot (14.6M records).')

if not os.path.exists(DATA):
    st.error('No data yet. Run `python pipeline/ingest.py <file>` and `python pipeline/build.py` first.')
    st.stop()
df = load()
evidence, stats, evaluation = load_extras()

accounts_tab, how_tab = st.tabs(['🎯 Accounts', '🔍 How it works'])
with how_tab:
    how_it_works(stats, evaluation)
with accounts_tab:
    accounts(df, evidence, set(stats.get('common_kev', [])))
