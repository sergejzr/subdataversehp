---
title: 'Upload of files less than 10 GB in size '
---
For files less than 10 GB in size, the standard upload over the Web GUI of DataPublication works well. 
You can upload single files or even whole folders. The number of the files does not matter much as long as no file is too large (i.e  is more than 10 GB). For automation you can try following tools:

**DVUploader**
The open-source DVUploader tool is a stand-alone command-line Java application that uses the Dataverse API to upload files to a specified dataset.  It is intended as an alternative to uploading files through the Dataverse Web GUI in situations where the web interface is inconvenient due to the number of files or file locations (spread across multiple directories, mixed with files that have already been uploaded or file types that should be excluded) or the need to automate uploads. 

For more information on this please consult the [Dataverse User Guide](https://guides.dataverse.org/en/latest/user/dataset-management.html#id36). 

Further information about the DVUploader can be found on the project's [GitHub repository](https://github.com/IQSS/dataverse-uploader).

**Using DVUploader via API:**

```
EXPORT YOUR_API_KEY="your_api_key"
```
```
EXPORT UPLOAD_FOLDER="/home/user/external_uploads"
```
```
EXPORT DATASET_DOI="doi:<DP-DOI-PREFIX>/FK2/XXXXXX"
```
```

```
```
java -jar DVUploader-v1.2.0beta3.jar -key="${YOUR_API_KEY}" -did="${DATASET_DOI}" -server=https://<DP-DOMAIN>/ -uploadviaserver "${UPLOAD_FOLDER}"
```


**For advanced users**

**Using the API Call**
The fastest way the user can upload a single file is using the API. In case your data is already on an institutional storage system (e.g. a [Coscine](https://about.coscine.de/) resource) mounted on a server with ssh access, you can use  the following call. Please only use it if you are really sure what you are doing. Please, also understand that we will likely not be able to help you debugging.

```
EXPORT YOUR_API_KEY="your_api_key"
```
```
EXPORT UPLOAD_FILE_LOCATION="/home/user/external_uploads/file.7z"
```
```
EXPORT DATASET_DOI="doi:<DP-DOI-PREFIX>/FK2/XXXXXX"
```
```
curl -vv -H "X-Dataverse-key:${YOUR_API_KEY}" -X POST -F file=@ "${UPLOAD_FILE_LOCATION}" -F 'jsonData={"description":" ","directoryLabel":"","categories":["Data"], "restrict":"false", "tabIngest":"false"}' "http://<DP-DOMAIN>/api/datasets/:persistentId/add?persistentId=${DATASET_DOI}" > /home/user/upload.log 2>&1 &
```