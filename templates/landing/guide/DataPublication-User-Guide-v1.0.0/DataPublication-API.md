---
title: DataPublication API
---
DataPublication provides a powerful set of APIs for data manipulation. A complete API guide can be found at the dataverse page: <https://guides.dataverse.org/en/latest/api/index.html>

## Token

To use the API a personal token is required. You can find/create this token in your profile at DataPublication:

![image-2024-2-14\_15-42-14](uploads/c0272276403376678bbd01a27d30818a/image-2024-2-14_15-42-14.png){width=900 height=403}

## Example usage

### Access metadata

For example you can list datasets and dataverses contained at DataPublication:

    export API_TOKEN=YOUR_TOKEN

    curl -H "X-Dataverse-key:$API_TOKEN" https://<DP-DOMAIN>/api/dataverses/1/contents
    #or
    curl -H "X-Dataverse-key:$API_TOKEN" https://<DP-DOMAIN>/api/dataverses/:root/contents
    #or
    curl -H "X-Dataverse-key:$API_TOKEN" https://<DP-DOMAIN>/api/dataverses/COLLECTION_ALIAS/contents

Example output (illustrative, shortened):

    {"status":"OK","data":[{"type":"dataverse","id":42,"title":"Example Collection"},{"id":3,"identifier":"FK2/XXXXXX","persistentUrl":"https://doi.org/<DP-DOI-PREFIX>/FK2/XXXXXX","protocol":"doi","authority":"<DP-DOI-PREFIX>","publisher":"DataPublication","publicationDate":"2026-01-01","metadataLanguage":"en","type":"dataset"}]}

> **[DP-TODO-04]** Beispiel-Response gegen die echte Instanz neu erzeugen, z.B.:
> `curl -s https://test.datapublication.nrw/api/dataverses/:root/contents`
> (Achtung: DOI-Prefix der Testinstanz ist vermutlich ein DataCite-Test-Prefix, nicht der Produktions-Prefix) — siehe DataPublication-OFFENE-PUNKTE.md

Having a doi you can get more information about the dataset

    export PERSISTENT_IDENTIFIER=doi:<DP-DOI-PREFIX>/FK2/XXXXXX

    curl -H "X-Dataverse-key:$API_TOKEN" "https://<DP-DOMAIN>/api/datasets/:persistentId/?persistentId=$PERSISTENT_IDENTIFIER"

### Access files

Any publicly available file at DataPublication can be accessed through its id

    https://<DP-DOMAIN>/api/access/datafile/int_id

## Libraries

There are some libraries in the language of your choice the can help you to interact with the API. We recommend very basic solutions though, because the API is changing fast and the user - managed  libraries become unstable from time to time. The basic libraries we recommend are:

  - Ubuntu/Shell: curl <https://curl.se/>
  - Python: requests <https://pypi.org/project/requests/>
  - Java: HTTPClient <https://hc.apache.org/httpcomponents-client-5.2.x/>

Also chatGPT was found to be very helpful to find particular methods for actions of your need. It will also provide code snippets in the language of your choice. Example prompt:

    I want to access harvard dataverse api and get all datasets of a dataverse. It should be a class where the constructor receives the dataverse URL and API token and dataverse label as parameters. Use Java.

Example output:

 Expand source

    import java.io.BufferedReader;
    import java.io.IOException;
    import java.io.InputStreamReader;
    import java.net.HttpURLConnection;
    import java.net.URL;

    public class HarvardDataverseAPI {
        private String baseUrl;
        private String apiToken;
        private String dataverseLabel;

        public HarvardDataverseAPI(String baseUrl, String apiToken, String dataverseLabel) {
            this.baseUrl = baseUrl;
            this.apiToken = apiToken;
            this.dataverseLabel = dataverseLabel;
        }

        public void getAllDatasets() {
            try {
                URL url = new URL(baseUrl + "/api/dataverses/" + dataverseLabel + "/contents");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("X-Dataverse-key", apiToken);

                BufferedReader in = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                String inputLine;
                StringBuilder response = new StringBuilder();

                while ((inputLine = in.readLine()) != null) {
                    response.append(inputLine);
                }
                in.close();

                System.out.println(response.toString());
                conn.disconnect();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }

        public static void main(String[] args) {
            String baseUrl = "https://your-dataverse-url.com";
            String apiToken = "your-api-token";
            String dataverseLabel = "your-dataverse-label";

            HarvardDataverseAPI api = new HarvardDataverseAPI(baseUrl, apiToken, dataverseLabel);
            api.getAllDatasets();
        }
    }
