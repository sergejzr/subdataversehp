---
title: Adding files to the dataset
---
To add files to your dataset upon its creation, please upload the data in the "Files" section of the metadata form.

If you wish to add files to your draft dataset after its creation, please go to "Edit Dataset" and click on "Files (Upload)".

Alternatively, you can also click on the button "Upload files" on the dataset's landing page.

**Please note:** that your files should be prepared such that they can be easily downloaded by users after the publication of the dataset. For large datasets (over 10 GB) and /or with many files (over 4.000), we recommend to get in touch with us (<DP-SUPPORT-MAIL>), so we can assist you with the data upload and finding the best structure for your dataset. For datasets, especially in the TB range, we recommend splitting your data into .zip folders, up to 50 GB and with less than 4.000 files each and following our upload recommendations listed in the respective subpages.

**Warning:**
Unfortunately, we have discovered that the DataPublication Web GUI has issues with large .zip files (approximately > 1 GB). Uploading is only possible via the API, and even then, there may be interruptions. If you would like to upload a large .zip file, please contact us (<DP-SUPPORT-MAIL>), as the upload will need to be handled through us. We are already working on a solution to this problem.

What currently works:

1. Uploading any number of smaller files (including folders) via the Web GUI usually works without any issues.
2. Uploading large files that are not in ".zip" format (such as RAR, 7Zip, .gz, .tar, etc.) works without problems. We recommend **7Zip** as archive format.
3. [DVUploader](https://github.com/GlobalDataverseCommunityConsortium/dataverse-uploader) generally works quite well too.
