---
title: Forschungssoftware und Code
---
![noun-code-1351169](uploads/808b870f334ff814d306d6a21d92e0b9/noun-code-1351169.png){width=150 height=202}

The FAIR4RS Principles for Research Software

**Hint:**

#### Practical resources:

  - Netherlands eScience Center and DANS: [Five Recommendations for FAIR Software](https://fair-software.eu/)
  - The Turing Way Community. (2022). [The Turing Way: A handbook for reproducible, ethical and collaborative research](https://doi.org/10.5281/zenodo.3233853). Zenodo. doi: 10.5281/zenodo.3233853.
  - Stall et al. (2023). [Software Documentation and Citation Checklist.](https://doi.org/10.5281/zenodo.7841908)  Zenodo.
  - Allen et al. (2025). [Ten simple rules for PIs to integrate Research Software Engineering into their research group.](https://doi.org/10.48550/arXiv.2506.20217)

Increasingly, **researchers develop** and modify code or **software** as part of their work. Thus, it is both a **research output** and a tool essential for the traceability and reproducibility of research results.

What is meant by research software here? Software is a vague term and can encompass many different things. From the perspective of the FAIR principles, it is particularly crucial that the software or code was generated **in the research process and for a research purpose**, thus being a research output:

**Research Software** includes source code files, algorithms, scripts, computational workflows and executables that were created during the research process or for a research purpose.
(Gruenpeter et al. (2021): [Defining Research Software: a controversial discussion](https://doi.org/10.5281/zenodo.5504016). Zenodo. S.16)

This differentiates research software from "software in research," meaning software that is merely used in the research context.

Definitions of research data typically include code and software explicitly, also to emphasize their significance for the reusability and transparency of research. At the same time, they represent a **special data type**. Unlike "conventional" research data, code and software are executable on a computer and are often continuously developed or integrated into other software. This presents unique challenges for archiving, making available, referencing, describing, and reusing code & software that the FAIR principles for research data do not adequately address.

Hence, specific **FAIR principles for research software (FAIR4RS)** were formulated to provide guidance for publishing and long-term preservation of research software:

  - **Findable:** The software and associated metadata are easy to find for both humans and machines. This requires persistent identifiers and rich metadata.
  - **Accessible:** The software and metadata can be retrieved via standard protocols. Therefore, the software should be open, free, and universally usable. If necessary, an authentication process should be implemented.
  - **Interoperable:** The software interacts with other software through the exchange of data or metadata or standardized API interfaces. Established community standards for data processing should also be considered.
  - **Reusable:** The software is not only executable but can also be understood, modified, extended, and integrated into other software. This also presupposes a clear licensing as well as extensive documentation.

**Hint:**

#### Further reading

  - Barkeret al. (2022) [Introducing the FAIR Principles for research software](https://doi.org/10.1038/s41597-022-01710-x). sdata 9, 622
  - Gruenpeter et al. (2021). [Defining Research Software: a controversial discussion](https://doi.org/10.5281/zenodo.5504016). Zenodo.
  - Bach et al. (2019): [Muster-Richtlinie Nachhaltige Forschungssoftware an den Helmholtz-Zentren](https://doi.org/10.2312/os.helmholtz.007), Potsdam : Helmholtz Open Science Office.
  - Deutsche Forschungsgemeinschaft. (2024). [Handling of Research Software in the DFG’s Funding Activities](https://doi.org/10.5281/zenodo.13919790)
  - [Further literature on research software](https://www.zotero.org/groups/4876461/rdsc_uni-bonn/tags/software/library)

Software Management Plan

**Hint:**

  - Create a Software Management Plan if software development plays a significant role in your project

#### Practical resources:

  - Grossmann, Y. V., & Franke, M. (2022). [Template “Software Management Plan for Researcher”](https://doi.org/10.17617/2.3481986)
  - Martinez-Ortiz, et al. (2023): [Practical guide to Software Management Plans](https://doi.org/10.5281/zenodo.7589725)
  - Beispiel: [openCARP Software Management Plan](https://opencarp.org/about/software-management-plan)
  - Alves et al. (2021): [ELIXIR Software Management Plan for Life Sciences](https://doi.org/10.37044/osf.io/k8znb)
  - ARDC: [FAIR for Jupyter Notebooks: A Practical Guide](https://ardc.edu.au/resource/fair-for-jupyter-notebooks-a-practical-guide)

The Software Management Plan (SMP) is akin to the concept of a Data Management Plan. The SMP is a tool to structure and proactively organize software management within a research project. The SMP defines the purpose and scope of the software and addresses practical issues of development and availability (e.g. version control, repository, documentation, testing procedures, or licensing). It also establishes responsibilities for publication, maintenance, support, and long-term accessibility of the software. Thus, the SMP helps to estimate the necessary resources for software work, carry out development according to plan, and ensure adherence to the FAIR4RS principles.

**Hint:**

#### Further reading

  - Software Sustainability Institute, 2018. [Checklist for a Software Management Plan](https://doi.org/10.5281/ZENODO.2159713)
  - [forschungsdaten.info](http://forschungsdaten.info): [Software Management Plans](https://forschungsdaten.info/praxis-kompakt/english-pages/software-management-plans/)

Version Control and Collaboration

**Hint:**

  - Use a repository with version control for code development

#### Practical resources:

  - Many institutions in NRW operate a local GitLab system for their members — check your institution’s IT services
  - Software Carpentries: [Version Control with Git](https://swcarpentry.github.io/git-novice/)
  - git training courses are regularly offered by many university IT centers

Version control offers many benefits for programming. Here are some of the key advantages:

1.  **History and traceability:** Version control allows the storage and tracking of changes in the source code over time. This makes it possible to compare changes and understand who made which changes.
2.  **Collaboration:** Multiple developers can work on the same project simultaneously without getting in each other's way. Version control enables the integration of changes and resolution of conflicts when multiple people work on the same files at the same time.
3.  **Branching and merging:** Developers can create independent branches to develop new features or experiments without affecting the main code. After successful development, these branches can be integrated back into the main code (merging).
4.  **Debugging:** In case of errors or bugs in the software, previous versions can be accessed to identify when the error was introduced. This significantly facilitates error analysis and resolution.
5.  **Backup and recovery:** Version control systems serve as a backup mechanism. If data is lost or an unexpected problem occurs, developers can revert to previous versions.
6.  **Documentation:** Every change in the code is logged, enabling detailed documentation of the development history. This can be useful for understanding decisions or documenting progress.

Git has established itself as one of the most powerful and flexible version control systems and is used in a wide variety of projects and organizations worldwide. The well-known development platform GitHub is also based on Git. Many institutions operate a local GitLab platform for their members. GitLab provides an integrated environment for version control, collaboration, and project management.

**Hint:**

#### Further reading

  - The Turing Way: [Version Control](https://the-turing-way.netlify.app/reproducible-research/vcs)
  - Chacon & Straub (2014): [Pro Git](https://git-scm.com/book/en/v2)

Documentation and comprehensebility of code

**Hint:**

  - Your code should be as understandable and traceable as possible
  - Adhere to formatting conventions and the Clean Code concept
  - Document your software, e.g., with a README file

#### Practical resources:

  - Berkeley Library: [How to Write Good Documentation](https://guides.lib.berkeley.edu/how-to-write-good-documentation)
  - [Awesome-Liste formatting conventions and best practices for different programming languages](https://github.com/Kristories/awesome-guidelines)
  - [Readme-Editor](https://readme.so/) von Katherine Oelsner
  - Write the Docs: [A beginner’s guide to writing documentation](https://www.writethedocs.org/guide/writing/beginners-guide-to-docs/)
  - Germán Cocca: [How to Write Clean Code – Tips and Best Practices](https://www.freecodecamp.org/news/how-to-write-clean-code/)

Documenting code is extremely important. Well-documented code makes it easier for new team members to quickly get involved in a project and facilitates collaboration, maintenance, and troubleshooting. Above all, it helps others (and your future self) to understand the code. Thus, documentation is a fundamental condition for traceability and reusability according to the FAIR4RS principles. Good documentation occurs on multiple levels:

  - Especially for larger or more complex projects, **general documentation** of the architecture and algorithms, e.g., using different types of [UML diagrams](https://de.wikipedia.org/wiki/Unified_Modeling_Language), is advisable. Every project should also have a README file with general information about the software and the license.
  - Documentation tools appropriate for the language (e.g., JavaDoc for Java) allow documenting **specific packages, classes, methods, or functions** directly in the source code and exporting them into a documentation document in different formats, e.g., HTML.
  - On an even deeper level, it may also be useful to explain **more complex conditions and code structures** with inline comments directly in the code. This will only be necessary in a few complex cases. However, this also depends on the experience and training of the project participants.

Additionally, the code itself should be as intuitively understandable as possible. Follow common conventions for style and formatting for your programming language. Moreover, the concept of "Clean Code" has been established, according to which code should not only work but also be easily understandable and maintainable for other developers.

Key principles of Clean Code include

  - **Readability:** Clean Code should be easy to read. This means that variables, functions, and classes should have meaningful names, and the code should be structured to promote reading flow.
  - **Self-explanatory:** The code should be written in a way that clearly expresses its intentions. Comments should be minimized, and the code itself should be so understandable that it almost reads like a natural language.
  - **Clarity and consistency:** The code should be consistently formatted to avoid confusion. Uniform naming conventions and structuring enhance clarity.
  - **Avoidance of redundancy:** Repetitions in the code should be avoided. This includes redundant variables, functions, or code blocks. Reusable functions should be outsourced to separate methods or functions. In object-oriented programming, the use of suitable design patterns is also recommended to avoid redundancy at higher levels.
  - **Small functions:** Functions should be short and focused. Ideally, each function should perform only one task. Short functions are easier to understand, test, and maintain.

**Hint:**

#### Further reading

  - Marcus et al. (2023): [HeFDI Code School: Sustainable Research Software - Clean Code and Refactoring](https://doi.org/10.5281/zenodo.10100081)
  - Documenting research data

 

Licenses for Research Software

**Hint:**

  - License your software to define the terms of use for third parties
  - In the spirit of FAIR4RS, choose licenses that are as free or open-source as possible

#### Practical resources:

  - Albert et al. (2019) [Copyright Guide for Scientific Software](https://doi.org/10.5281/ZENODO.3581326)
  - Software Sustainability Institute: [Choosing an open-Source licence](https://www.software.ac.uk/resources/guides/choosing-open-source-licence)

Licenses for software play a crucial role as they regulate the legal **conditions under which software can be used**, copied, distributed, modified, and shared (see also usage licenses for research data). Software licenses define the rights and obligations of users regarding the use of the software. In line with FAIR4RS, research software should ideally be licensed under permissive licenses  that are **as open as possible** and only as closed as necessary. Generally, you should opt for **free or open-source software licenses** to ensure that the software can be freely accessed, used, modified, and shared by anyone. Although free and open-source licenses share many similarities, they come from different traditions, which can sometimes affect the compatibility of different licenses. For example, free software licenses often include a copyleft, which "inherits" the license conditions to all derivatives of the software. A very permissive and widely used open-source license is the [MIT License](https://opensource.org/license/mit/). Popular licenses with copyleft include the [GNU GPL](https://opensource.org/license/gpl-3-0/) or the [GNU LGPL](https://opensource.org/license/lgpl-3-0/) (with restricted copyleft).

**Hint:**

#### Further reading

  - [IfrOSS Licence Center](https://ifross.github.io/ifrOSS/Pages/licence_center/de)
  - [Software Licenses in Plain English](https://www.tldrlegal.com/)
  - [Licenses of the Free Software Foundation](https://www.gnu.org/licenses/)

Publishing and archiving research software

**Hint:**

  - Publish your research software in a citable form in software archives or repositories

According to good research practice and the FAIR4RS principles, research software constitutes central results of research work. Therefore, it should be published in a citable manner and made available in the long term, just like traditional text publications or research data. If the software is already on central platforms such as GitLab or GitHub, a significant step towards availability has been taken. However, for proper citation, it must be clear which point in time or which version the citation refers to. Moreover, long-term availability is not guaranteed on git-based development platforms, especially not the stability of URLs to the respective projects. Therefore, it is advisable to additionally publish the software through a software archive or a data repository, where the software is provided with a persistent identifier specific to the version. Ideally, there is already a suitable **software archive for your scientific community**. Such an archive can be found among the members of [SciCodes, the "Consortium of scientific software registries and repositories,"](https://scicodes.net/participants/) or through a search for [code repositories at re3data](https://www.re3data.org/search?query=&contentTypes%5B%5D=Source%20code). Another option is the publication of a **snapshot of the code on general data repositories** like [Zenodo](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content) or the [local repository DataPublication](https://<DP-DOMAIN>/). A third option is the [**Software Heritage Archive**](https://archive.softwareheritage.org/save/) hosted in France.

To give research software a more significant role in scientific discourse, publication in a specialized [**software journal**](https://www.software.ac.uk/top-tip/which-journals-should-i-publish-my-software) might also be worthwhile.

#### Further reading

  - Beyer et al. (2025). [Publishing research code FAIR - a roadmap](https://doi.org/10.5281/zenodo.14772749) 

  - **Hint:** Anzt et al. (2020): [An environment for sustainable research software in Germany and beyond: current state, open challenges, and call for action](https://doi.org/10.12688/f1000research.23224.1). F1000Res 9, 295.

  - Fehr, J., Himpe, C., Rave, S., Saak, J., 2021. [Sustainable Research Software Hand-Over](https://doi.org/10.5334/jors.307)

  - Morrissey, S.M., 2020. [Preserving Software: Motivations, Challenges and Approaches](https://doi.org/10.7207/twgn20-02). Digital Preservation Coalition.

  - Publishing and archiving research data

←  Publishing and archiving research data

Discipline-specific resources →
