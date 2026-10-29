# Evaluation report

## Back-test: do the warning signs find servers that were actually breached?

- Breached servers (compromised tag or open database): 56 of 3,350,096
- AUC of the score without breach signals: **0.701** (0.5 = random, 1.0 = perfect)
- Breached servers are **6.0x** over-represented in the 10,000 highest-scoring servers

## Lift: how much more often servers with each signal are breached (1.0 = no effect)

| signal       |   hosts |   lift |
|:-------------|--------:|-------:|
| eol          |  162153 |  15.13 |
| high_epss    |  295947 |   2.43 |
| kev          |  189882 |   1.89 |
| cert_expired |   35681 |   1.68 |
| self_signed  |   85000 |   0.70 |
| remote       |   26341 |   0.00 |
| legacy_tls   |   57113 |   0.00 |
| anon_ftp     |     957 |   0.00 |
| ntlm         |   20321 |   0.00 |
| waf          |   77804 |   0.00 |
| security_txt |    4247 |   0.00 |

## Accounts per tier

| tier                     |      n |
|:-------------------------|-------:|
| Low signal               | 113458 |
| Vulnerable software      |  59173 |
| Poor hygiene             |  45423 |
| Actively exploited CVE   |   8304 |
| Exposed critical service |   2636 |
| Breached / data exposed  |      3 |

## Spot check: top 25

| company        | tier                     |   risk_score | country   |   ips |   ownership | network_org                                               | web_title                                                       |
|:---------------|:-------------------------|-------------:|:----------|------:|------------:|:----------------------------------------------------------|:----------------------------------------------------------------|
| berkeley.edu   | Actively exploited CVE   |          162 | US        |   511 |        0.89 | University of California at Berkeley                      | KSLabServer/Login                                               |
| usp.br         | Actively exploited CVE   |          144 | BR        |   230 |        1    | UNIVERSIDADE DE SAO PAULO                                 | Grafana                                                         |
| rit.edu        | Actively exploited CVE   |          143 | US        |   288 |        0.89 | Rochester Institute of Technology                         | Accessible Learning Labs                                        |
| mit.edu        | Actively exploited CVE   |          138 | US        |   268 |        0.79 | Massachusetts Institute of Technology                     | wattsworth                                                      |
| keymachine.de  | Actively exploited CVE   |          135 | DE        |   800 |        0.88 | Keyweb AG IP Network                                      | One moment, please...                                           |
| eztech.vn      | Actively exploited CVE   |          131 | VN        |    57 |        0    | VNONE Vietnam Company Limited                             | TMV HRM Docs                                                    |
| ritesim.com    | Actively exploited CVE   |          130 | NL        |   150 |        0    | Ritesim.com Limited                                       | WEB                                                             |
| nazwa.pl       | Actively exploited CVE   |          129 | PL        |  3104 |        0.94 | webhosting servers                                        | Domena  jest utrzymywana na serwerach nazwa.pl                  |
| keio.ac.jp     | Actively exploited CVE   |          128 | JP        |    73 |        0.91 | Keio University                                           | Welcome to nginx!                                               |
| uoc.gr         | Exposed critical service |          128 | GR        |    75 |        1    | University of Crete                                       | Login to Webmin                                                 |
| go.com.jo      | Actively exploited CVE   |          127 | JO        |    77 |        0    | Jordan Telecom Group (Orange)                             | Wireless - Administrative Console                               |
| edu.hu         | Actively exploited CVE   |          127 | HU        |    41 |        0.5  | KIFU (Governmental Info Tech Development Agency)          | SuliXerver - Portál                                             |
| hpe.com        | Actively exploited CVE   |          125 | US        |   159 |        0.99 | HEWLETT PACKARD ENTERPRISE COMPANY                        | InsightVM Security Console :: Login                             |
| grnet.gr       | Actively exploited CVE   |          125 | GR        |   133 |        0.8  | National Infrastructures for Research and Technology S.A. | BRIDGE                                                          |
| verunix.com.tr | Actively exploited CVE   |          124 | TR        |    96 |        0.4  | danis danisman                                            | Default Web Site Page                                           |
| netart.com     | Actively exploited CVE   |          123 | PL        |   321 |        0.77 | webhosting servers                                        | 502 Bad Gateway                                                 |
| cnr.it         | Actively exploited CVE   |          118 | IT        |   191 |        0.97 | Consiglio Nazionale delle Ricerche                        | https:// required                                               |
| webhorizon.net | Actively exploited CVE   |          115 | CH        |    26 |        0    | Abc-Hosters LLC                                           | SSL VPN Service                                                 |
| bnr.la         | Actively exploited CVE   |          114 | AU        |    78 |        0.26 | Mammoth Media Pty Ltd                                     | 21 miles — Tutoring &amp; learning support, Preschool to Year 6 |
| noez.de        | Exposed critical service |          114 | DE        |   112 |        0.25 | GHOSTnet GmbH                                             | Welcome to nginx!                                               |
| vndata.vn      | Exposed critical service |          113 | VN        |    20 |        0    | VIET STORAGE TECHNOLOGY JOINT STOCK COMPANY               | Welcome to nginx!                                               |
| slt.lk         | Exposed critical service |          113 | LK        |   133 |        1    | ADSL - DYNAMIC POOL                                       | Remote Surveillance, Any time &amp; Any where                   |
| zun.com        | Exposed critical service |          112 | HK        |    16 |        0    | Tisson Ritar Technology Limited                           | 404 Not Found                                                   |
| webmasters.com | Actively exploited CVE   |          110 | US        |    28 |        0.92 | KUDUCOM                                                   | 208.64.140.30 - Coming Soon!                                    |
| ucdavis.edu    | Actively exploited CVE   |          110 | US        |    87 |        0.95 | University of California, Davis                           | Web Filter Block Override                                       |

## Spot check: random 25

| company               | tier                   |   risk_score | country   |   ips |   ownership | network_org                               | web_title                                                                                          |
|:----------------------|:-----------------------|-------------:|:----------|------:|------------:|:------------------------------------------|:---------------------------------------------------------------------------------------------------|
| myschooljumper.ie     | Actively exploited CVE |           66 | IE        |     1 |           1 | INFRA-AW                                  | nan                                                                                                |
| afpgeodezja.pl        | Actively exploited CVE |           65 | DE        |     1 |           1 | OVH GmbH                                  | AFP Geodezja Usługi Geodezyjne Gorzów Wlkp. - Geodeta Piotr Foltyński                              |
| passalot.eu.com       | Vulnerable software    |           43 | FR        |     2 |         nan | E-Internet S.C. TomaHost                  | Apache HTTP Server Test Page powered by CentOS                                                     |
| pneusbelisle.com      | Vulnerable software    |           41 | CA        |     1 |           0 | Linode                                    | Integra Tire | Pneus et service automobile                                                         |
| financelho.eu         | Vulnerable software    |           41 | LT        |     1 |         nan | UAB Bacloud                               | Welcome to nginx!                                                                                  |
| aegis6.com            | Vulnerable software    |           41 | CN        |     1 |           1 | China Unicom Liaoning province network    | nan                                                                                                |
| northernguild.org     | Vulnerable software    |           33 | GB        |     2 |         nan | 34SP.com Ltd.                             | nan                                                                                                |
| ispot.cc              | Vulnerable software    |           21 | US        |     3 |           1 | Interserver, Inc                          | Success!                                                                                           |
| scadatenders.com      | Vulnerable software    |           12 | US        |     1 |         nan | HostPapa                                  | HTTP Server Test Page powered by CentOS-WebPanel.com                                               |
| dickersons.net        | Vulnerable software    |           12 | US        |     1 |         nan | Newtek Technology Solutions, Inc          | nan                                                                                                |
| worldofplayer.com     | Vulnerable software    |           12 | US        |     1 |         nan | B2 Net Solutions Inc.                     | nan                                                                                                |
| lyzhxgt.com           | Poor hygiene           |           11 | HK        |     3 |           1 | LUOGELANG (FRANCE) LIMITED                | 功能模块及系统标签等等介绍 - 苹果CMS                                                                              |
| saludbcs.gob.mx       | Vulnerable software    |           10 | MX        |     1 |         nan | Gestión de direccionamiento UniNet        | nan                                                                                                |
| the-gym.com.ua        | Vulnerable software    |            8 | DE        |     1 |           1 | Contabo GmbH                              | THE GYM — Фітнес-центр                                                                             |
| serviciodesoporte.com | Poor hygiene           |            8 | ES        |     1 |           1 | arsys.es                                  | Plesk Obsidian 18.0.81                                                                             |
| gomaxrx.com           | Poor hygiene           |            7 | US        |     1 |           1 | Amazon Technologies Inc.                  | MaxRx | Fast, Discreet Men&#x27;s Health &amp; Online Prescriptions                                |
| y-place.jp            | Poor hygiene           |            7 | JP        |     1 |           0 | Amazon Data Services Japan                | 小児科・内科・アレルギー科 はたクリニック（ふじみ野市・富士見市・三芳町等）                                                             |
| butler-style.co.jp    | Poor hygiene           |            7 | JP        |     1 |           0 | SAKURA Internet Inc.                      | �d�C�H���S�� �򕌂̃��[���h�d��                                                                        |
| soojungcn.com         | Poor hygiene           |            7 | US        |     1 |           0 | Cogent Communications, LLC                | nan                                                                                                |
| devgenii.hr           | Poor hygiene           |            7 | DE        |     1 |           0 | DigitalOcean, LLC                         | nan                                                                                                |
| infin8cg.com          | Poor hygiene           |            7 | US        |     1 |           1 | NuCDN LLC                                 | One moment, please...                                                                              |
| syowahimawari-sr.com  | Poor hygiene           |            7 | JP        |     1 |           0 | Amazon Data Services Japan                | 瀬谷区の歯医者・歯科医院なら新谷歯科医院                                                                               |
| vvdntech.in           | Poor hygiene           |            6 | US        |     1 |           1 | Amazon Technologies Inc.                  | Global Provider of Software, Product Engineering, Electronics Manufacturing Services and Solutions |
| antpool.com           | Poor hygiene           |            5 | SG        |     1 |           1 | Alibaba Cloud (Singapore) Private Limited | nan                                                                                                |
| muveranai.com         | Vulnerable software    |            5 | CH        |     1 |           1 | Akenes SA                                 | RK Iglesias Platform                                                                               |
