# Sources and Retrieval Register

This repository publishes tools, equation summaries, and citations, not downloaded
third-party catalogs, PDFs, measurements, meshes, software source archives, or private
design reports. Links document provenance; they do not grant redistribution rights.

## Catalogs and Driver Inputs

| Source | Link | Role/status |
|---|---|---|
| Separate Parts Express snapshot repository | https://github.com/meowelectronics/parts-express-database | Existing external catalog; clone/download locally, not bundled here |
| Parts Express | https://www.parts-express.com/ | Original storefront for component specifications, prices, and manufacturer resources |
| SoundImports | https://www.soundimports.eu/ | Original EU supplier reference; any snapshot remains external |
| WinISD | https://www.linearteam.org/ | External software/source of user-supplied `.wdr` inputs; records are not redistributed |
| Loudspeaker Database | https://loudspeakerdatabase.com/ | Requested source; live retrieval returned HTTP 520 on 2026-10-02; no dataset imported |
| Loudspeaker Database alternate host | https://www.loudspeakerdatabase.com/ | Also returned HTTP 520 |
| Robots rules | https://loudspeakerdatabase.com/robots.txt | Retrieved to inspect crawler rules; not a data license |
| Sitemap | https://loudspeakerdatabase.com/sitemap.xml | Retrieval returned HTTP 520 |

The WinISD import originated from a user-provided local directory. Its original drive
path and all driver records are excluded from this public repository. Use an explicit
directory when importing your own authorized files.

Parts Express categories used in the original acquisition workflow include woofers,
midrange/midbass/fullrange drivers, subwoofers, tweeters, passive radiators, planar/ribbon
transducers, horn-loaded tweeters/midranges, air-core/solid-core/copper-foil inductors,
wirewound resistors, and film/foil/polypropylene/non-polar electrolytic capacitors.
Exact category, product, PDF, ZIP, and manufacturer-resource URLs are recorded in
[FETCH_LINKS.json](FETCH_LINKS.json). This inventory includes resource links found in
catalog snapshots, even when there is no proof that each individual resource was downloaded.

## Measurement and Design References

- [ASR quasi-anechoic measurements, REW, and VituixCAD discussion](https://www.audiosciencereview.com/forum/index.php?threads/how-to-make-quasi-anechoic-speaker-measurements-spinoramas-with-rew-and-vituixcad.21860/).
- [Crover documentation](https://crover.app/docs).
- [Crover calculators](https://crover.app/en/calculators).
- [Crover FRD/ZMA workflow](https://crover.app/en/create-frd-zma-files).
- [Crover REW impedance workflow](https://crover.app/en/measure-impedance-rew-zma).
- [00aud loudspeaker simulator](https://simulator.00aud.io/app): public application reference; source maps were unavailable.
- [Scimpy](https://github.com/maqifrnswa/scimpy): GPL-3.0 upstream algorithm/workflow reference; source tree not bundled.
- [SpeakerSim](https://github.com/LightBit/SpeakerSim): GPL-3.0 upstream algorithm/workflow reference; source tree not bundled.

Books cited as reference works: Vance Dickason, *The Loudspeaker Design Cookbook*,
7th edition; Glen M. Ballou (ed.), *Handbook for Sound Engineers*, 4th edition;
F. Alton Everest, *The Master Handbook of Acoustics*, 4th edition. No book texts,
tables, or scans are bundled. A privately supplied design manual was part of the
original investigation but is not included or required by this project.

VituixCAD help, a user-supplied HTGuide index, and a Reddit page were also discussed
in the original research. The retained provenance does not contain their exact URLs
or usable extracted content, so this register does not invent addresses or claim
successful retrieval. Unavailable sources are marked in the knowledge seed.

## Unverified Mirror Leads

The following appeared in GitHub search while the Loudspeaker Database site was
unavailable. Their inspection was cancelled; none is verified as an official mirror,
licensed dataset, or imported source:

- https://github.com/wangzhenjjcn/loudspeakerdatabase
- https://github.com/Johnlon/LoudspeakerDatabase
- https://github.com/OddNaughty/loudspeakerdatabase_crawling

## Inventory Limits and Rights

[FETCH_LINKS.json](FETCH_LINKS.json) retains all recoverable source/resource URLs from
the catalog snapshots, acquisition scripts, and retained documentation, plus the
documented failed fetch attempts above. It is a link inventory, not a complete network
request log. It cannot establish that every link was actually fetched or successfully
parsed. No fetched content is bundled with it.

Respect each source's license, terms, robots rules, attribution requirements, and
request limits. Public availability is not permission to copy or redistribute.
The Parts Express repository currently exposes data files without a visible license
in its root; confirm rights before redistributing those snapshots. Retain timestamps,
identities, source hashes, measurement context, and unit definitions in local imports.