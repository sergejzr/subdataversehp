---
title: Upload of files between 10 GB and 100 GB
---
For files over 10 GB it will not be possible to use the DataPublication Web GUI, API, or DVUploader anymore. We offer an SFTP solution for uploading large files, in this case our team has to be involved. The solution consists of following steps:

1. Install FileZilla (or another SFTP client). Downloads and documentation are available at the [FileZilla project page](https://filezilla-project.org/).

2. Create an SSH key pair (e.g. with `ssh-keygen` or the PuTTY tools on Windows).

3. Contact our team in advance in order to discuss what sizes / file types are possible for your dataset. We provide a project storage for uploading large files to DataPublication.

4. After creating the key pair, please send your public key (usually the file with the ending .pub) to us (<DP-SUPPORT-MAIL>).

5. Create a FileZilla connection using the private key:

Host: **[DP-TODO-03: SFTP-Host]**
User name / standard path: **[DP-TODO-03: Nutzername/Pfad]**
Logon Type: Keyfile

Key: Path to the private key (that you created in step 2.)

**Important!** sometimes Filezilla can not "see" the private key, because it does not have any file extension. You can add to your filename the extension ".pem" and it should work.

6. Upload your files by connecting to the storage and access your group folder. Please, upload your files to your folder. You are free to structure your group folder as you wish.

**IMPORTANT!** Do not change anything on the server besides the contents of your own group folder! This is a trust based procedure. In case it happened by mistake, and you changed the contents of a different folder, tell us ASAP and we will restore the contents!

7. Tell us about your files: Kindly tell us about your file structure and supply us with a relation FILENAME - Dataset-ID and we shall add the files to the corresponding dataset (the dataset should already exist in DataPublication).

8. After the files are uploaded, please verify the contents of the dataset to make sure everything is as you requested.

9. After a successful upload, your key will be disabled by our team. The key can be enabled again anytime by contacting us.

> **[DP-TODO-03]** Gesamter SFTP-Workflow war bonndata/FDI-spezifisch (Host `fdi-projekte.uni-bonn.de`, Pfad `/hrz_userupload`, HRZ-Confluence-Doku). Für DataPublication klären: Gibt es ein SFTP-Angebot? Host, Nutzername, Pfad, Doku-Links — siehe `DataPublication-OFFENE-PUNKTE.md`
