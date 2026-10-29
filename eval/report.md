# Evaluation report

## Back-test: do the warning signs find servers that were actually breached?

- Breached servers (compromised tag or open database): 56 of 3,350,096
- AUC of the score without breach signals: **0.803** (0.5 = random, 1.0 = perfect)
- Breached servers are **6.0x** over-represented in the 10,000 highest-scoring servers

## Lift: how much more often servers with each signal are breached (1.0 = no effect)

| signal       |   hosts |   lift |
|:-------------|--------:|-------:|
| eol          |  162156 |  15.13 |
| high_epss    |  295947 |   2.43 |
| kev          |  189880 |   1.89 |
| cert_expired |   35677 |   1.68 |
| self_signed  |   84983 |   0.70 |
| remote       |   26364 |   0.00 |
| legacy_tls   |   57112 |   0.00 |
| anon_ftp     |     957 |   0.00 |
| ntlm         |   20328 |   0.00 |
| waf          |   77782 |   0.00 |
| security_txt |    4258 |   0.00 |

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

| company        | tier                     |   risk_score | country   |   ips |   ownership | network_org                                               | web_title                                      |
|:---------------|:-------------------------|-------------:|:----------|------:|------------:|:----------------------------------------------------------|:-----------------------------------------------|
| berkeley.edu   | Actively exploited CVE   |          162 | US        |   511 |        0.89 | University of California at Berkeley                      | PowerAlert Device Manager                      |
| usp.br         | Actively exploited CVE   |          144 | BR        |   230 |        1    | UNIVERSIDADE DE SAO PAULO                                 | Welcome to nginx!                              |
| rit.edu        | Actively exploited CVE   |          143 | US        |   288 |        0.89 | Rochester Institute of Technology                         | Flexs Q5                                       |
| mit.edu        | Actively exploited CVE   |          138 | US        |   268 |        0.79 | Massachusetts Institute of Technology                     | Media Browser                                  |
| keymachine.de  | Actively exploited CVE   |          135 | DE        |   800 |        0.88 | Keyweb AG IP Network                                      | Default Parallels Plesk Page                   |
| eztech.vn      | Actively exploited CVE   |          131 | VN        |    57 |        0    | VNONE Vietnam Company Limited                             | Sorry, the website has been stopped            |
| ritesim.com    | Actively exploited CVE   |          130 | NL        |   150 |        0    | Ritesim.com Limited                                       | Login                                          |
| nazwa.pl       | Actively exploited CVE   |          129 | PL        |  3104 |        0.94 | webhosting servers                                        | Domena  jest utrzymywana na serwerach nazwa.pl |
| keio.ac.jp     | Actively exploited CVE   |          128 | JP        |    73 |        0.91 | Keio University                                           | Login – Nextcloud                              |
| uoc.gr         | Exposed critical service |          128 | GR        |    75 |        1    | University of Crete                                       | Login to Webmin                                |
| go.com.jo      | Actively exploited CVE   |          127 | JO        |    77 |        0    | Jordan Telecom Group (Orange)                             | https:// required                              |
| edu.hu         | Actively exploited CVE   |          127 | HU        |    41 |        0.5  | KIFU (Governmental Info Tech Development Agency)          | IIS Windows Server                             |
| grnet.gr       | Actively exploited CVE   |          125 | GR        |   133 |        0.8  | National Infrastructures for Research and Technology S.A. | Apache2 Ubuntu Default Page: It works          |
| hpe.com        | Actively exploited CVE   |          125 | US        |   159 |        0.99 | HEWLETT PACKARD ENTERPRISE COMPANY                        | HPE RDA                                        |
| verunix.com.tr | Actively exploited CVE   |          124 | TR        |    96 |        0.4  | danis danisman                                            | Sorry, the website has been stopped            |
| netart.com     | Actively exploited CVE   |          123 | PL        |   321 |        0.77 | webhosting servers                                        | Domain  is hosted on netart.com servers        |
| cnr.it         | Actively exploited CVE   |          118 | IT        |   191 |        0.97 | Consiglio Nazionale delle Ricerche                        | https:// required                              |
| webhorizon.net | Actively exploited CVE   |          115 | CH        |    26 |        0    | Abc-Hosters LLC                                           | SSL VPN Service                                |
| bnr.la         | Actively exploited CVE   |          114 | AU        |    78 |        0.26 | Mammoth Media Pty Ltd                                     | Welcome to nginx!                              |
| noez.de        | Exposed critical service |          114 | DE        |   112 |        0.25 | GHOSTnet GmbH                                             | Welcome to nginx!                              |
| vndata.vn      | Exposed critical service |          113 | VN        |    20 |        0    | VIET STORAGE TECHNOLOGY JOINT STOCK COMPANY               | IIS Windows Server                             |
| slt.lk         | Exposed critical service |          113 | LK        |   133 |        1    | ADSL - DYNAMIC POOL                                       | ::: Login :::                                  |
| zun.com        | Exposed critical service |          112 | HK        |    16 |        0    | Tisson Ritar Technology Limited                           | welcome use kangle!                            |
| ucdavis.edu    | Actively exploited CVE   |          110 | US        |    87 |        0.95 | University of California, Davis                           | quantum-simulation.org                         |
| netsys.am      | Actively exploited CVE   |          110 | AM        |    23 |        0    | Netsys JVC is internet services provider in Armeina       | Netsys ISP                                     |

## Spot check: random 25

| company                   | tier                     |   risk_score | country   |   ips |   ownership | network_org                                 | web_title                                          |
|:--------------------------|:-------------------------|-------------:|:----------|------:|------------:|:--------------------------------------------|:---------------------------------------------------|
| schleussner-net.de        | Actively exploited CVE   |           66 | DE        |     1 |        1    | 1&1 Telecom GmbH                            | nan                                                |
| tninetwork.com            | Vulnerable software      |           65 | CA        |     3 |        1    | Microsoft Corporation                       | TNI Agency Websites |                              |
| the-insurance-broker.com  | Vulnerable software      |           43 | GB        |     2 |        1    | Kualo Limited                               | Get a Quote | The Insurance Broker Ltd             |
| sprava-siti.net           | Vulnerable software      |           41 | CZ        |     1 |      nan    | Coolhousing s.r.o.                          | Test Page for the Nginx HTTP Server on Rocky Linux |
| shamautoparts.com         | Vulnerable software      |           41 | CA        |     1 |        1    | DigitalOcean, LLC                           | SHAM AUTOPARTS BILL GENERATOR                      |
| featuredesk.app           | Vulnerable software      |           41 | AE        |     1 |      nan    | Hetzner Online GmbH                         | nan                                                |
| homarik.ru                | Vulnerable software      |           33 | DE        |     1 |      nan    | OVH SAS                                     | nan                                                |
| active-concepts.at        | Vulnerable software      |           21 | GB        |     1 |        1    | Hetzner Online GmbH                         | Login – Nextcloud                                  |
| nineweb.net               | Vulnerable software      |           12 | TH        |    10 |        0.95 | Internet Thailand Company Ltd.              | Default Web Site Page                              |
| simulistics.com           | Vulnerable software      |           12 | DE        |     1 |      nan    | Linode, LLC                                 | Apache2 Debian Default Page: It works              |
| trendset.de               | Exposed critical service |           12 | DE        |     1 |      nan    | M-net Telekommunikations GmbH               | nan                                                |
| zhihuiky.com              | Poor hygiene             |           11 | CN        |     1 |        1    | Tencent cloud computing (Beijing) Co., Ltd. | 萤火商城2.0                                            |
| delasport.com             | Poor hygiene             |           10 | US        |     1 |        1    | Google LLC                                  | nan                                                |
| riverviewmanagement.com   | Poor hygiene             |            8 | US        |     1 |        1    | HostGator.com LLC                           | Contact Support                                    |
| usha15.ru                 | Poor hygiene             |            8 | RU        |     1 |        1    | Beget LLC                                   | GlitchTip                                          |
| servprobrightonhowell.com | Poor hygiene             |            7 | US        |     1 |        0    | Amazon Technologies Inc.                    | nan                                                |
| jiffy.ai                  | Poor hygiene             |            7 | IN        |     2 |        1    | Amazon Technologies Inc.                    | ERS - Error                                        |
| hndansai.com              | Poor hygiene             |            7 | US        |     1 |        0    | POWER LINE DATACENTER                       | nan                                                |
| iohealthtech.com          | Poor hygiene             |            7 | US        |     1 |        1    | Amazon Technologies Inc.                    | IOHealth Portal                                    |
| revendus.com.br           | Poor hygiene             |            7 | US        |     1 |        1    | HIVELOCITY, Inc.                            | nan                                                |
| gotrg.dev                 | Poor hygiene             |            7 | US        |     1 |        1    | Google LLC                                  | nan                                                |
| lcjym.com                 | Poor hygiene             |            7 | CN        |     1 |        1    | Tencent Cloud Computing (Beijing) Co., Ltd  | 聊城金友鸣锅炉配件有限公司 - 耐热耐磨特种钢铸件研发定制与销售                   |
| simpleworks.info          | Poor hygiene             |            6 | JP        |     1 |        1    | Vultr Holdings, LLC                         | nan                                                |
| inpk.link                 | Poor hygiene             |            5 | KR        |     1 |        0    | AWS Asia Pacific (Seoul) Region             | 위너 소재를 찾는 인플루언서 마케팅, 인포크비즈니스                       |
| ykq-vedkzvvjtq-njd.icu    | Poor hygiene             |            5 | US        |     1 |        0    | Cogent Communications, LLC                  | 正在加载中...                                           |
