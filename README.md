# Cluster Generator (QGIS Plugin)

**Cluster Generator** creates cluster polygons from point, line, and polygon layers in QGIS.
It is designed for workflows where objects with the same attribute value should be represented by a single cluster area.
The plugin package in this ZIP is intended for **QGIS 3.x and QGIS 4.x**.

## 

## Main capabilities

* Create cluster polygons from **point, line, or polygon** input layers
* Use an **attribute field** to group source objects into clusters
* Create a **single cluster for the whole layer** when no attribute is selected
* Optionally restrict processing to **selected features only**
* Optionally clip results with a **boundary layer**
* Create **temporary output** or save the result to disk
* Store the cluster name in the **`name`** field
* Apply categorized styling and label the result from **`name`**
* Use incrementing temporary output names such as **\_01, \_02, \_03**
* Support multilingual UI behavior inside QGIS

## 

## Intended use

This plugin is useful when you want to:

* represent service areas for distribution points
* group addresses, cables, buildings, or other network objects by an attribute
* generate cluster polygons for technical review, planning, and visual analysis
* work consistently in both **QGIS 3.x** and **QGIS 4.x** without maintaining separate packages

## 

## Installation in QGIS

1. Download this ZIP file.
2. Open **QGIS**.
3. Go to **Plugins → Manage and Install Plugins → Install from ZIP**.
4. Select this ZIP file and install it.

## 

## Notes

* The plugin supports **point, line, and polygon** input layers.
* If no attribute is selected, the plugin can create **one cluster for the whole input layer**.
* If a boundary layer is provided, the generated clusters are clipped to that boundary.
* If no output path is set, the result is created as a temporary layer.

## 

## Author

**Senol Baskaya**  
📧 senolbaskaya@gmail.com

🌍 \[LinkedIn] (https://www.linkedin.com/in/senolbaskaya/)

\---

## 

## License

MIT License

