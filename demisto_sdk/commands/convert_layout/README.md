## Download

**Convert layouts from new version to old version and vice versa.**

In order to run the command, `DEMISTO_BASE_URL` environment variable should contain the Demisto base URL, and `DEMISTO_API_KEY` environment variable should contain a valid Demisto API Key.
To set the environment variables, run the following shell commands:
```
export DEMISTO_BASE_URL=<YOUR_DESMISTO_BASE_URL>
export DEMISTO_API_KEY=<YOUR_DEMISTO_API_KEY>
```


### Use Cases
This command is used to convert old versioned layouts (Demisto version <6.0) to new versioned layouts (Demisto version >=6.0).


### Arguments
* **-i PACK_PATH, --input PACK_PATH**

    The path of a package directory that contains the layouts to be converted.

* **-stf, --six-to-five**

    Whether to convert new layouts to old layouts or not.

* **-fts, --five-to-six**

    Whether to convert old layouts to new layouts or not.

### Examples
```
demisto-sdk convert-layout -i Packs/TestPack1 -i Packs/TestPack2
```
This will convert all layouts (both old and new versions) in "TestPack1" & "TestPack2" packs to their opposite version.
If non of the flags is provided, the default behaviour is that they are both turned on, i.e. converting in both directions.
<br/><br/>
```
demisto-sdk convert-layout -i Packs/TestPack1 -stf
```
This will convert all new layouts in TestPack1 pack to their corresponding old format.
<br/><br/>
```
demisto-sdk convert-layout -i Packs/TestPack1 -fts
```
This will convert all old layouts in TestPack1 pack to their corresponding new format.
<br/><br/>
