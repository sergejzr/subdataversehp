---
title: Editing files
---
If you would like to:

- restrict access to all of your files or just specific ones,
- delete files,
- replace files,
- edit file metadata and move files to subfolders

you can do so by selecting the file in question (if the file is selected, it is highlighted yellow) and clicking on the "Edit files" button.

Upon file selection, you can also click on the three vertical dots icon to access the "File Options" menu for each file independently.

![meta_4](uploads/1cfef56397d7148ee82c005ba0194a5a/meta_4.png){width=267 height=165}




**Restricting files**

When a file is restricted, it cannot be downloaded unless permission has been granted. Restricted files cannot be previewed.
In order to restrict files, after selecting the appropriate file and accessing the "Edit Options" menu, choose the option "Restrict". To revoke a restriction on a file select the file, access the "Edit Options" menu and click on "Unrestrict".

![restrict-1](uploads/02ce7c6f151f0a6fac37bd2c5bcc7236/restrict-1.png){width=892 height=518}

A "Restrict Access" pop-up window will appear where you can enable / disable "Request Access" and provide "Terms of Access for Restricted Files".

![restrict-2](uploads/a7afc4c58f1f9f7ee50283193f9e1236/restrict-2.png){width=852 height=431}

By default, the "Request Access" option is enabled. When filled out, the "Terms of Access for restricted Files" become visible in the "Terms" tab and upon selection of the "Terms" option in the "Edit Dataset" dropdown menu. There you can also provide more information regarding access to restricted files (see 3.5 Choosing appropriate licenses for your research data)XXXXX.


**Placing files in subfolders / editing a file path**

The "File Path" metadata field is a Dataverse installation’s way of representing a file’s location in a folder structure. If a user downloads the full dataset or a selection of files from it, they will receive a folder structure with each file positioned according to its file path. Only one file with a given path and name may exist in a dataset. Editing a file to give it the same path and name as another file already existing in the dataset will cause an error.

A file’s file path can be manually added or edited on the "Edit Files" page. Changing a file’s file path will change its location in the folder structure that is created when a user downloads the full dataset or a selection of files from it.

when there is more than one file in the dataset, and once at least one of the files has a non-empty directory path, the Dataset landing page will present an option for switching between the traditional table view, and the tree-like view of the files showing the folder structure, as in the example below:

![file-tree-view](uploads/18b420009c8c9aa9bdcc717b776fd5a8/file-tree-view.png){width=419 height=375}