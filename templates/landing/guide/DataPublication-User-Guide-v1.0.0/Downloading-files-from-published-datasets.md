---
title: Downloading files from published datasets
---
If you would like to download all files in a dataset, you can click on the *Access Dataset*  button on the dataset's page and select one of the download options from the dropdown Menu. The dataset’s files will be downloaded as a .zip  and any folder structure that the dataset owner had set up will be preserved.

If you’d like to download a single file,  a subset or all of the dataset’s files, you can also do so via the *Files* tab: select the files you would like to download and then click on the *Download* button located above the files. Again, a .zip package will be generated and any folder structure that the dataset owner had set up will be preserved.

**Please note:** In case of very large datasets (10 GB in size and more), it is not possible to generate a .zip file encompassing all of the dataset files. In such cases, please select the files you would like to download manually, via the *Files* tab.

Alternatively you can use the Harvard Dataverse Downloader (finetuning and further development in progress, feedback is very welcome): <https://github.com/sergejzr/harvard-dataverse-downloader>

Further information can be found also at the [Dataverse User Guide](https://guides.dataverse.org/en/5.3/user/find-use-data.html#id15) webpage.

**Please note:** Please note that files within a dataset you would like to download can be organized in one or more folders (directories). If the folder structure is defined, an option for switching between the traditional table view, and the tree-like view showing folder and file hierarchy will be presented, similarly as in the example below:

![image-file-tree-view](https://guides.dataverse.org/en/latest/_images/file-tree-view.png)

You can switch between the two views by clicking on the respective button.

Please note that downloading options are only displayed in the table view.

Taken from the [Dataverse User Guide](https://guides.dataverse.org/en/latest/user/find-use-data.html?highlight=tree%20view#tree-view) webpage.

## 6.1 Download of large datasets \>20GB

Unfortunately, there are yet problems downloading datasets \> 20GB using the Web interface.

In this cases we recommend using the Harvard Dataverse Downloader ((finetuning and further development in progress, feedback is very welcome)): <https://github.com/sergejzr/harvard-dataverse-downloader>

or you can also use the command wget

    EXPORT URL="https://<DP-DOMAIN>/api/access/datafile/:persistenId?persistenId=doi:<DP-DOI-PREFIX>/FK2/XXXX/XXXX"
    wget -c $URL || wget -c $URL

    #we need to call wget two times as it unfortunately breaks down after first 20GB
