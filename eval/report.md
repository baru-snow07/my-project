# Evaluation report

## Back-test: do the warning signs find servers that were actually breached?

- Breached servers (compromised tag or open database): 56 of 3,350,096
- AUC of the score without breach signals: **0.701** (0.5 = random, 1.0 = perfect)
- Breached servers are **6.0x** over-represented in the 10,000 highest-scoring servers

## Lift: how much more often servers with each signal are breached (1.0 = no effect)

| signal       |   hosts |   lift |
|:-------------|--------:|-------:|
| eol          |  162144 |  15.13 |
| high_epss    |  295946 |   2.43 |
| kev          |  189871 |   1.89 |
| cert_expired |   35665 |   1.68 |
| self_signed  |   84994 |   0.70 |
| remote       |   26480 |   0.00 |
| legacy_tls   |   57120 |   0.00 |
| anon_ftp     |     957 |   0.00 |
| ntlm         |   20326 |   0.00 |
| waf          |   77793 |   0.00 |
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

| company        | tier                     |   risk_score | country   |   ips |   ownership | network_org                                               | web_title                                     |
|:---------------|:-------------------------|-------------:|:----------|------:|------------:|:----------------------------------------------------------|:----------------------------------------------|
| berkeley.edu   | Actively exploited CVE   |          162 | US        |   511 |        0.89 | University of California at Berkeley                      | PowerAlert Device Manager                     |
| usp.br         | Actively exploited CVE   |          144 | BR        |   230 |        1    | UNIVERSIDADE DE SAO PAULO                                 | Welcome to nginx!                             |
| rit.edu        | Actively exploited CVE   |          143 | US        |   288 |        0.89 | Rochester Institute of Technology                         | Media Browser                                 |
| mit.edu        | Actively exploited CVE   |          138 | US        |   268 |        0.79 | Massachusetts Institute of Technology                     | Ceph Exporter                                 |
| keymachine.de  | Actively exploited CVE   |          135 | DE        |   800 |        0.88 | Keyweb AG IP Network                                      | Web Server's Default Page                     |
| eztech.vn      | Actively exploited CVE   |          131 | VN        |    57 |        0    | VNONE Vietnam Company Limited                             | Welcome to nginx!                             |
| ritesim.com    | Actively exploited CVE   |          130 | NL        |   150 |        0    | Ritesim.com Limited                                       | Login                                         |
| nazwa.pl       | Actively exploited CVE   |          129 | PL        |  3104 |        0.94 | webhosting servers                                        | 502 Bad Gateway                               |
| uoc.gr         | Exposed critical service |          128 | GR        |    75 |        1    | University of Crete                                       | Login to Webmin                               |
| keio.ac.jp     | Actively exploited CVE   |          128 | JP        |    73 |        0.91 | Keio University                                           | 慶應義塾先端科学技術研究センター &#8211; KLL                  |
| edu.hu         | Actively exploited CVE   |          127 | HU        |    41 |        0.5  | KIFU (Governmental Info Tech Development Agency)          | SuliXerver - Portál                           |
| go.com.jo      | Actively exploited CVE   |          127 | JO        |    77 |        0    | Jordan Telecom Group (Orange)                             | https:// required                             |
| hpe.com        | Actively exploited CVE   |          125 | US        |   159 |        0.99 | HEWLETT PACKARD ENTERPRISE COMPANY                        | HPE RDA                                       |
| grnet.gr       | Actively exploited CVE   |          125 | GR        |   133 |        0.8  | National Infrastructures for Research and Technology S.A. | Apache2 Ubuntu Default Page: It works         |
| verunix.com.tr | Actively exploited CVE   |          124 | TR        |    96 |        0.4  | danis danisman                                            | Welcome to nginx!                             |
| netart.com     | Actively exploited CVE   |          123 | PL        |   321 |        0.77 | webhosting servers                                        | Domain  is hosted on netart.com servers       |
| cnr.it         | Actively exploited CVE   |          118 | IT        |   191 |        0.97 | Consiglio Nazionale delle Ricerche                        | Blitzortung.org Controller 19.5 :: Status     |
| webhorizon.net | Actively exploited CVE   |          115 | CH        |    26 |        0    | Abc-Hosters LLC                                           | Welcome to nginx!                             |
| noez.de        | Exposed critical service |          114 | DE        |   112 |        0.25 | GHOSTnet GmbH                                             | Welcome to nginx!                             |
| bnr.la         | Actively exploited CVE   |          114 | AU        |    78 |        0.26 | Mammoth Media Pty Ltd                                     | Welcome to nginx!                             |
| slt.lk         | Exposed critical service |          113 | LK        |   133 |        1    | ADSL - DYNAMIC POOL                                       | Remote Surveillance, Any time &amp; Any where |
| vndata.vn      | Exposed critical service |          113 | VN        |    20 |        0    | VIET STORAGE TECHNOLOGY JOINT STOCK COMPANY               | Welcome to nginx!                             |
| zun.com        | Exposed critical service |          112 | HK        |    16 |        0    | Tisson Ritar Technology Limited                           | Test Page for Apache Installation             |
| webmasters.com | Actively exploited CVE   |          110 | US        |    28 |        0.92 | KUDUCOM                                                   | 51.81.90.48 - Coming Soon!                    |
| netsys.am      | Actively exploited CVE   |          110 | AM        |    23 |        0    | Netsys JVC is internet services provider in Armeina       | RegionNet — Админ панель                      |

## Spot check: random 25

| company                         | tier                   |   risk_score | country   |   ips |   ownership | network_org                                         | web_title                                                                                            |
|:--------------------------------|:-----------------------|-------------:|:----------|------:|------------:|:----------------------------------------------------|:-----------------------------------------------------------------------------------------------------|
| deliverylake.com                | Actively exploited CVE |           66 | DE        |     1 |        0    | Hetzner Online GmbH                                 | nan                                                                                                  |
| toyo-tos.co.jp                  | Actively exploited CVE |           65 | JP        |     1 |        1    | FUJITSU CLOUD TECHNOLOGIES LIMITED                  | 株式会社 東陽                                                                                              |
| websitesource.net               | Vulnerable software    |           43 | US        |     2 |      nan    | Alentus Corporation                                 | Parallels H-Sphere                                                                                   |
| autopasscorp.com                | Vulnerable software    |           41 | BR        |     1 |        1    | Amazon Technologies Inc.                            | nan                                                                                                  |
| paloauto.fi                     | Vulnerable software    |           41 | FI        |     1 |      nan    | UpCloud Cloud Servers                               | nan                                                                                                  |
| ripson.ru                       | Vulnerable software    |           41 | RU        |     1 |        1    | Beget LLC                                           | nan                                                                                                  |
| navajotech.edu                  | Vulnerable software    |           33 | US        |     1 |      nan    | DigitalOcean, LLC                                   | nan                                                                                                  |
| gpac-licensing.com              | Vulnerable software    |           21 | DE        |     1 |        0    | Hetzner Online GmbH                                 | Motion Spell&#39;s git                                                                               |
| pages4web.de                    | Vulnerable software    |           12 | DE        |     1 |        0    | Strato GmbH                                         | Domain Default page                                                                                  |
| bollsoft.de                     | Vulnerable software    |           12 | DE        |     1 |      nan    | Deutsche Telekom AG                                 | nan                                                                                                  |
| vlasimnet.cz                    | Vulnerable software    |           12 | CZ        |     1 |      nan    | Vlasimnet s.r.o.                                    | nan                                                                                                  |
| jng3l1.com                      | Poor hygiene           |           11 | HK        |     1 |        1    | Alibaba Cloud LLC                                   | 恭喜，站点创建成功！                                                                                           |
| javapipe.com                    | Poor hygiene           |           10 | US        |     1 |        0    | Nexeon Technologies, Inc.                           | nan                                                                                                  |
| iyasaka.co.jp                   | Poor hygiene           |            8 | JP        |     1 |        1    | Sony Network Communications Inc.                    | nan                                                                                                  |
| beivo.sk                        | Poor hygiene           |            8 | SK        |     1 |        1    | VNET a.s.                                           | nan                                                                                                  |
| sanggt.com                      | Low signal             |            7 | DE        |     1 |        1    | Hetzner Online GmbH                                 | Index of /                                                                                           |
| dongjinim.co.kr                 | Poor hygiene           |            7 | KR        |     1 |        0    | Korea Telecom                                       | nan                                                                                                  |
| tomaru-tatemono.jp              | Poor hygiene           |            7 | JP        |     2 |        0    | Amazon Data Services Japan                          | 奈良で損害保険相談・リスクコンサルは保険代理店スマート・アイ                                                                       |
| harrisonsford.co.uk             | Poor hygiene           |            7 | GB        |     1 |        0.33 | Heart Internet Ltd                                  | New & Used Cars, Servicing, MOT - Ford Dealer Scotland (Cupar, Dalkeith, Kirkcaldy, Peebles, Dundee) |
| csair.cn                        | Poor hygiene           |            7 | CN        |     3 |        1    | China Unicom Guangdong province network             | nan                                                                                                  |
| room347.com                     | Poor hygiene           |            7 | JP        |     1 |        1    | Amazon Web Services, Elastic Compute Cloud, EC2, JP | Welcome to nginx!                                                                                    |
| kyujin-nakanishidc.jp           | Poor hygiene           |            7 | JP        |     1 |        0    | Amazon Data Services Japan                          | nan                                                                                                  |
| fontaine.com                    | Poor hygiene           |            6 | US        |     1 |        1    | Unified Layer                                       | Global Fontaine Fifth Wheel ... fifthwheel.com                                                       |
| ecomgroup.co                    | Poor hygiene           |            5 | GB        |     1 |        0    | Trident Net Limited                                 | Web Server's Default Page                                                                            |
| my.firewall_7fbb436d_01344f9d84 | Poor hygiene           |            5 | CA        |     1 |        1    | TELUS Communications Inc.                           | Quantum Spark Security Appliance - Login                                                             |
