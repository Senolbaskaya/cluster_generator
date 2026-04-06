import os
import traceback

from qgis.PyQt.QtCore import QVariant, QLocale, QSettings
from qgis.PyQt.QtGui import QAction, QColor, QIcon, QFont
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QFileDialog, QLineEdit, QCheckBox, QProgressBar, QApplication
)
from qgis.core import (
    Qgis, QgsProject, QgsVectorLayer, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsUnitTypes, QgsField, QgsFeature, QgsGeometry,
    QgsSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsVectorFileWriter,
    QgsWkbTypes, QgsApplication, QgsTextFormat, QgsTextBufferSettings,
    QgsFeatureRequest, QgsRectangle
)
from qgis import processing


class ClusterGenerator:
    TEXTS = {
        "title": {"en": "Cluster Generator", "de": "Cluster Generator", "tr": "Cluster Oluşturucu", "es": "Generador de Clústeres"},
        "input_layer": {"en": "Input layer:", "de": "Input-Layer:", "tr": "Girdi katmanı:", "es": "Capa de entrada:"},
        "selected_only": {"en": "Use selected features only", "de": "Nur ausgewählte Objekte verwenden", "tr": "Sadece seçili objeleri kullan", "es": "Usar solo objetos seleccionados"},
        "boundary": {"en": "Boundary layer (optional):", "de": "Boundary-Layer (optional):", "tr": "Sınır katmanı (opsiyonel):", "es": "Capa límite (opcional):"},
        "field": {"en": "Attribute field:", "de": "Attributfeld:", "tr": "Öznitelik alanı:", "es": "Campo de atributo:"},
        "output": {"en": "Output (optional, default: temporary):", "de": "Ausgabe (optional, Standard: temporär):", "tr": "Çıktı (opsiyonel, varsayılan: geçici):", "es": "Salida (opcional, por defecto: temporal):"},
        "choose_file": {"en": "Select file", "de": "Datei wählen", "tr": "Dosya seç", "es": "Seleccionar archivo"},
        "save_file": {"en": "Select output file", "de": "Ausgabedatei wählen", "tr": "Çıktı dosyasını seç", "es": "Seleccionar archivo de salida"},
        "none": {"en": "<None>", "de": "<Keine>", "tr": "<Yok>", "es": "<Ninguna>"},
        "create": {"en": "Create clusters", "de": "Cluster erstellen", "tr": "Cluster oluştur", "es": "Crear clústeres"},
        "error": {"en": "Error", "de": "Fehler", "tr": "Hata", "es": "Error"},
        "success": {"en": "Success", "de": "Erfolg", "tr": "Başarılı", "es": "Correcto"},
        "missing": {"en": "Input layer is missing.", "de": "Input-Layer fehlt.", "tr": "Girdi katmanı eksik.", "es": "Falta la capa de entrada."},
        "field_not_found": {"en": "The selected attribute field was not found.", "de": "Das gewählte Attributfeld wurde nicht gefunden.", "tr": "Seçilen öznitelik alanı bulunamadı.", "es": "No se encontró el campo de atributo seleccionado."},
        "no_selected": {"en": "No features are selected.", "de": "Es sind keine Objekte ausgewählt.", "tr": "Hiç obje seçili değil.", "es": "No hay objetos seleccionados."},
        "no_features": {"en": "No features found inside the analysis area.", "de": "Keine Objekte innerhalb der Analysefläche gefunden.", "tr": "Analiz alanında obje bulunamadı.", "es": "No se encontraron objetos dentro del área de análisis."},
        "no_seeds": {"en": "No seed points could be created.", "de": "Es konnten keine Seed-Punkte erzeugt werden.", "tr": "Tohum noktaları üretilemedi.", "es": "No se pudieron crear puntos semilla."},
        "bad_geom": {"en": "Unsupported geometry type.", "de": "Nicht unterstützter Geometrietyp.", "tr": "Desteklenmeyen geometri tipi.", "es": "Tipo de geometría no compatible."},
        "saved_fail": {"en": "Could not save output layer.", "de": "Ausgabe konnte nicht gespeichert werden.", "tr": "Çıktı katmanı kaydedilemedi.", "es": "No se pudo guardar la capa."},
        "load_fail": {"en": "Saved layer could not be loaded.", "de": "Gespeicherter Layer konnte nicht geladen werden.", "tr": "Kaydedilen katman yüklenemedi.", "es": "No se pudo cargar la capa guardada."},
        "done": {"en": "Cluster layer was created.", "de": "Cluster-Layer wurde erstellt.", "tr": "Cluster katmanı oluşturuldu.", "es": "La capa de clúster se creó."},
    }

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None
        self.layer_combo = None
        self.field_combo = None
        self.boundary_combo = None
        self.output_edit = None
        self.output_button = None
        self.selected_only_cb = None
        self.progress = None
        self.run_button = None
        self.log_tag = "ClusterGenerator"
        self.plugin_dir = os.path.dirname(__file__)

    def _lang(self):
        try:
            # Read the active QGIS UI locale first and fall back to the OS locale only if needed.
            qs = QSettings()
            override = str(qs.value("locale/overrideFlag", "false")).lower() in ("1", "true", "yes")
            ui_locale = str(qs.value("locale/userLocale", "") or "").lower()
            if override and ui_locale:
                name = ui_locale
            elif ui_locale:
                # QGIS often stores the active UI locale here even when the override flag is not enabled.
                name = ui_locale
            else:
                name = QLocale.system().name().lower()
        except Exception:
            name = "en"
        if name.startswith("de"):
            return "de"
        if name.startswith("tr"):
            return "tr"
        if name.startswith("es"):
            return "es"
        return "en"

    def _t(self, key):
        lang = self._lang()
        return self.TEXTS.get(key, {}).get(lang) or self.TEXTS.get(key, {}).get("en", key)

    def _exec_dialog(self, dlg):
        if hasattr(dlg, "exec"):
            return dlg.exec()
        return dlg.exec_()

    def _set_progress(self, value):
        if self.progress:
            self.progress.setValue(int(value))
            QApplication.processEvents()

    def log(self, message, level=Qgis.MessageLevel.Info):
        QgsApplication.messageLog().logMessage(str(message), self.log_tag, level)

    def push(self, title, msg, level=Qgis.MessageLevel.Info, duration=6):
        self.iface.messageBar().pushMessage(title, msg, level=level, duration=duration)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, self._t("title"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("Cluster Generator", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("Cluster Generator", self.action)
            self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.dlg = QDialog(self.iface.mainWindow())
        self.dlg.setWindowTitle(self._t("title"))

        root = QVBoxLayout()
        form = QFormLayout()

        self.layer_combo = QComboBox()
        self.boundary_combo = QComboBox()
        self.field_combo = QComboBox()
        self.output_edit = QLineEdit()
        self.output_button = QPushButton(self._t("choose_file"))
        self.selected_only_cb = QCheckBox(self._t("selected_only"))
        self.run_button = QPushButton(self._t("create"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        form.addRow(QLabel(self._t("input_layer")), self.layer_combo)
        form.addRow(QLabel(""), self.selected_only_cb)
        form.addRow(QLabel(self._t("boundary")), self.boundary_combo)
        form.addRow(QLabel(self._t("field")), self.field_combo)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit)
        output_row.addWidget(self.output_button)
        form.addRow(QLabel(self._t("output")), output_row)

        root.addLayout(form)
        root.addWidget(self.progress)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.run_button)
        root.addLayout(button_row)

        self.dlg.setLayout(root)
        self._populate_layers()
        self.layer_combo.currentIndexChanged.connect(self._populate_fields)
        self.output_button.clicked.connect(self._choose_output)
        self.run_button.clicked.connect(self.process)
        self._exec_dialog(self.dlg)

    def _populate_layers(self):
        self.layer_combo.clear()
        self.boundary_combo.clear()
        vector_layers = [
            l for l in QgsProject.instance().mapLayers().values()
            if isinstance(l, QgsVectorLayer) and l.isValid()
        ]
        for layer in vector_layers:
            self.layer_combo.addItem(layer.name(), layer)
        self.boundary_combo.addItem(self._t("none"), None)
        for layer in vector_layers:
            if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry:
                self.boundary_combo.addItem(layer.name(), layer)
        self._populate_fields()

    def _populate_fields(self):
        self.field_combo.clear()
        self.field_combo.addItem(self._t("none"), None)
        layer = self.layer_combo.currentData()
        if not layer:
            return
        for fld in layer.fields():
            self.field_combo.addItem(fld.name(), fld.name())

    def _choose_output(self):
        path, _ = QFileDialog.getSaveFileName(self.dlg, self._t("save_file"), "", "Shapefile (*.shp)")
        if path:
            if not path.lower().endswith(".shp"):
                path += ".shp"
            self.output_edit.setText(path)

    def _suggest_metric_crs(self, layer):
        # Perform metric operations in a projected CRS. Geographic CRSs such as EPSG:4326 are
        # reprojected to a local metric CRS before buffer, spacing, and partition calculations.
        crs = layer.crs()
        if not crs or not crs.isValid():
            return QgsCoordinateReferenceSystem("EPSG:3857")
        try:
            if (not crs.isGeographic()) and (crs.mapUnits() == QgsUnitTypes.DistanceMeters):
                return crs
        except Exception:
            pass
        if crs.isGeographic():
            try:
                wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
                xform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
                center = xform.transform(layer.extent().center())
                lon, lat = center.x(), center.y()
                zone = int((lon + 180.0) / 6.0) + 1
                epsg = 32600 + zone if lat >= 0 else 32700 + zone
                return QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
            except Exception:
                return QgsCoordinateReferenceSystem("EPSG:3857")
        return QgsCoordinateReferenceSystem("EPSG:3857")

    def _fix(self, layer):
        return processing.run("native:fixgeometries", {"INPUT": layer, "OUTPUT": "memory:"})["OUTPUT"]

    def _reproject_if_needed(self, layer, target_crs):
        if layer is None:
            return None
        if layer.crs().authid() == target_crs.authid():
            return layer
        return processing.run("native:reprojectlayer", {
            "INPUT": layer, "TARGET_CRS": target_crs, "OUTPUT": "memory:"
        })["OUTPUT"]

    def _selected_or_all(self, layer):
        if not self.selected_only_cb.isChecked():
            return layer
        selected_count = int(layer.selectedFeatureCount())
        self.log(f"selected_only requested | source={layer.featureCount()} | selected_count={selected_count}")
        if selected_count <= 0:
            raise RuntimeError(self._t("no_selected"))
        try:
            selected = processing.run("native:saveselectedfeatures", {
                "INPUT": layer,
                "OUTPUT": "memory:"
            })["OUTPUT"]
        except Exception as e:
            self.log(f"saveselectedfeatures fallback triggered: {e}")
            selected_features = list(layer.selectedFeatures())
            if not selected_features:
                raise RuntimeError(self._t("no_selected"))
            selected = QgsVectorLayer(
                f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}",
                f"{layer.name()}_selected",
                "memory"
            )
            pr = selected.dataProvider()
            pr.addAttributes(layer.fields())
            selected.updateFields()
            feats = []
            for feat in selected_features:
                new_feat = QgsFeature(selected.fields())
                new_feat.setGeometry(feat.geometry())
                new_feat.setAttributes(feat.attributes())
                feats.append(new_feat)
            if not feats:
                raise RuntimeError(self._t("no_selected"))
            pr.addFeatures(feats)
            selected.updateExtents()
        if selected.featureCount() == 0:
            raise RuntimeError(self._t("no_selected"))
        self.log(f"selected_only active | source={layer.featureCount()} | selected={selected_count} | working={selected.featureCount()}")
        return selected

    def _selected_group_values(self, layer, field_name):
        values = set()
        if not field_name:
            return values
        for feat in layer.getSelectedFeatures():
            try:
                val = feat[field_name]
            except Exception:
                val = None
            if val is not None:
                values.add(str(val))
        return values

    def _prepare_selected_mode_layer(self, layer, group_field):
        selected_count = int(layer.selectedFeatureCount())
        self.log(f"selected_only requested | source={layer.featureCount()} | selected_count={selected_count}")
        if selected_count <= 0:
            raise RuntimeError(self._t("no_selected"))

        delete_value = "__DELETE__" if group_field else "0"
        keep_name = "__SELECTED__" if not group_field else None
        temp_field = "_cg_group"

        out = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}",
            f"{layer.name()}_selected_mode",
            "memory"
        )
        pr = out.dataProvider()
        out_fields = layer.fields()
        if out_fields.lookupField(temp_field) >= 0:
            temp_field = "_cg_grp"
        pr.addAttributes(out_fields)
        pr.addAttributes([QgsField(temp_field, QVariant.String, len=254)])
        out.updateFields()

        selected_ids = set(layer.selectedFeatureIds())
        temp_idx = out.fields().lookupField(temp_field)
        feats = []
        for feat in layer.getFeatures():
            new_feat = QgsFeature(out.fields())
            new_feat.setGeometry(feat.geometry())
            attrs = list(feat.attributes())
            attrs.append(None)
            new_feat.setAttributes(attrs)
            is_selected = feat.id() in selected_ids
            if group_field:
                if is_selected:
                    try:
                        raw = feat[group_field]
                    except Exception:
                        raw = None
                    value = str(raw) if raw is not None else delete_value
                else:
                    value = delete_value
            else:
                value = keep_name if is_selected else delete_value
            new_feat.setAttribute(temp_idx, value)
            feats.append(new_feat)
        pr.addFeatures(feats)
        out.updateExtents()
        self.log(f"selected mode layer active | source={layer.featureCount()} | selected={selected_count} | working={out.featureCount()} | mode_field={temp_field}")
        return out, temp_field, delete_value

    def _default_domain_distance(self, layer):
        ext = layer.extent()
        max_dim = max(ext.width(), ext.height())
        if max_dim <= 0:
            return 10.0
        return max(5.0, min(50.0, max_dim * 0.10))

    def _selected_domain(self, layer):
        combined = self._combine_layer_geometry(layer)
        if combined is None or combined.isEmpty():
            return self._extent_domain(layer)
        try:
            hull = combined.convexHull()
        except Exception:
            hull = combined
        if hull is None or hull.isEmpty():
            hull = combined
        distance = self._default_domain_distance(layer)
        try:
            domain_geom = hull.buffer(float(distance), 8)
        except Exception:
            domain_geom = hull
        if domain_geom is None or domain_geom.isEmpty():
            return self._extent_domain(layer)
        out = QgsVectorLayer(f"Polygon?crs={layer.crs().authid()}", "selected_domain", "memory")
        pr = out.dataProvider()
        pr.addAttributes([QgsField("id", QVariant.Int)])
        out.updateFields()
        feat = QgsFeature(out.fields())
        feat.setGeometry(domain_geom)
        feat.setAttribute("id", 1)
        pr.addFeatures([feat])
        out.updateExtents()
        return self._fix(out)

    def _extent_domain(self, layer):
        domain = processing.run("native:polygonfromlayerextent", {
            "INPUT": layer, "ROUND_TO": 0, "OUTPUT": "memory:"
        })["OUTPUT"]
        distance = self._default_domain_distance(layer)
        domain = processing.run("native:buffer", {
            "INPUT": domain, "DISTANCE": float(distance), "SEGMENTS": 8,
            "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
            "DISSOLVE": True, "OUTPUT": "memory:"
        })["OUTPUT"]
        return self._fix(domain)

    def _boundary_domain(self, boundary_layer):
        domain = self._fix(boundary_layer)
        domain = processing.run("native:dissolve", {"INPUT": domain, "FIELD": [], "OUTPUT": "memory:"})["OUTPUT"]
        return self._fix(domain)


    def _intersect_domains(self, primary_domain, secondary_domain):
        try:
            inter = processing.run("native:intersection", {
                "INPUT": primary_domain,
                "OVERLAY": secondary_domain,
                "INPUT_FIELDS": [],
                "OVERLAY_FIELDS": [],
                "OVERLAY_FIELDS_PREFIX": "",
                "OUTPUT": "memory:"
            })["OUTPUT"]
            inter = self._fix(inter)
            if inter and inter.featureCount() > 0:
                return inter
        except Exception as e:
            self.log(f"domain intersection fallback: {e}")
        return secondary_domain

    def _build_count_map(self, layer, field_name):
        count_map = {}
        if not field_name:
            return {layer.name(): layer.featureCount()}
        for feat in layer.getFeatures():
            value = feat[field_name]
            if value is None:
                continue
            key = str(value)
            count_map[key] = count_map.get(key, 0) + 1
        return count_map

    def _boundary_sample_points(self, grouped_polys, field_name, spacing):
        boundary = processing.run("native:boundary", {"INPUT": grouped_polys, "OUTPUT": "memory:"})["OUTPUT"]
        pts = processing.run("native:pointsalonglines", {
            "INPUT": boundary, "DISTANCE": float(spacing), "START_OFFSET": 0.0,
            "END_OFFSET": 0.0, "OUTPUT": "memory:"
        })["OUTPUT"]
        return pts

    def _merge_group_polygons_back(self, partition, base_polys, field_name):
        grouped = {}
        for src in base_polys.getFeatures():
            key = str(src[field_name])
            geom = src.geometry()
            if geom is None or geom.isEmpty():
                continue
            grouped[key] = QgsGeometry(geom) if key not in grouped else grouped[key].combine(geom)
        out = QgsVectorLayer(f"Polygon?crs={partition.crs().authid()}", "merged_partition", "memory")
        pr = out.dataProvider()
        pr.addAttributes([QgsField(field_name, QVariant.String)])
        out.updateFields()
        feats = []
        for feat in partition.getFeatures():
            value = feat[field_name]
            if value is None:
                continue
            key = str(value)
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            if key in grouped:
                try:
                    geom = geom.combine(grouped[key])
                except Exception:
                    pass
            if geom is None or geom.isEmpty():
                continue
            f = QgsFeature(out.fields())
            f.setGeometry(geom)
            f.setAttribute(field_name, key)
            feats.append(f)
        pr.addFeatures(feats)
        out.updateExtents()
        dissolved = processing.run("native:dissolve", {"INPUT": out, "FIELD": [field_name], "OUTPUT": "memory:"})["OUTPUT"]
        return self._fix(dissolved)

    def _make_seed_points(self, layer):
        geom_type = QgsWkbTypes.geometryType(layer.wkbType())
        if geom_type == QgsWkbTypes.PointGeometry:
            return layer
        if geom_type == QgsWkbTypes.LineGeometry:
            extent = layer.extent()
            max_dim = max(extent.width(), extent.height())
            step = max(5.0, min(20.0, max_dim / 400.0 if max_dim > 0 else 8.0))
            return processing.run("native:pointsalonglines", {
                "INPUT": layer, "DISTANCE": step, "START_OFFSET": 0.0,
                "END_OFFSET": 0.0, "OUTPUT": "memory:"
            })["OUTPUT"]
        if geom_type == QgsWkbTypes.PolygonGeometry:
            return processing.run("native:pointonsurface", {
                "INPUT": layer, "ALL_PARTS": True, "OUTPUT": "memory:"
            })["OUTPUT"]
        raise RuntimeError(self._t("bad_geom"))

    def _create_single_group_layer(self, domain_layer, field_name, group_value):
        out = QgsVectorLayer(f"Polygon?crs={domain_layer.crs().authid()}", "single_cluster", "memory")
        pr = out.dataProvider()
        pr.addAttributes([QgsField(field_name, QVariant.String)])
        out.updateFields()
        feats = []
        for feat in domain_layer.getFeatures():
            f = QgsFeature(out.fields())
            f.setGeometry(feat.geometry())
            f.setAttribute(field_name, str(group_value))
            feats.append(f)
        pr.addFeatures(feats)
        out.updateExtents()
        return out

    def _smooth_geom(self, geom, distance):
        if geom is None or geom.isEmpty() or distance <= 0:
            return geom
        try:
            smoothed = geom.buffer(distance, 4).buffer(-distance, 4)
            if smoothed and not smoothed.isEmpty():
                return smoothed
        except Exception:
            pass
        return geom

    def _smoothed_layer(self, layer, field_name, distance):
        if distance <= 0:
            return self._fix(layer)
        out = QgsVectorLayer(f"Polygon?crs={layer.crs().authid()}", "smoothed", "memory")
        pr = out.dataProvider()
        pr.addAttributes([QgsField(field_name, QVariant.String)])
        out.updateFields()
        feats = []
        for feat in layer.getFeatures():
            value = feat[field_name]
            if value is None:
                continue
            geom = self._smooth_geom(feat.geometry(), distance)
            if geom is None or geom.isEmpty():
                continue
            f = QgsFeature(out.fields())
            f.setGeometry(geom)
            f.setAttribute(field_name, str(value))
            feats.append(f)
        pr.addFeatures(feats)
        out.updateExtents()
        return self._fix(out)

    def _partition_from_seeds(self, seeds, domain, field_name):
        # Use Voronoi cells as the base partition and clip the result back to the analysis domain.
        values_idx = seeds.fields().lookupField(field_name)
        unique_values = [v for v in seeds.uniqueValues(values_idx) if v is not None]
        if len(unique_values) == 1:
            return self._create_single_group_layer(domain, field_name, str(unique_values[0]))

        ext = domain.extent()
        max_dim = max(ext.width(), ext.height())
        vor_buffer = max(20.0, max_dim * 0.10)
        voronoi = processing.run("qgis:voronoipolygons", {
            "INPUT": seeds, "BUFFER": vor_buffer, "OUTPUT": "memory:"
        })["OUTPUT"]

        joined = processing.run("native:joinattributesbylocation", {
            "INPUT": voronoi,
            "JOIN": seeds,
            "PREDICATE": [0],
            "JOIN_FIELDS": [field_name],
            "METHOD": 0,
            "DISCARD_NONMATCHING": True,
            "OUTPUT": "memory:"
        })["OUTPUT"]

        partition = processing.run("native:dissolve", {
            "INPUT": joined, "FIELD": [field_name], "OUTPUT": "memory:"
        })["OUTPUT"]
        partition = processing.run("native:clip", {
            "INPUT": partition, "OVERLAY": domain, "OUTPUT": "memory:"
        })["OUTPUT"]
        return self._fix(partition)

    def _polygon_partition(self, in_analysis, domain, field_name):
        base_polys = processing.run("native:dissolve", {
            "INPUT": in_analysis, "FIELD": [field_name], "OUTPUT": "memory:"
        })["OUTPUT"]
        base_polys = self._fix(base_polys)
        unique_values = [v for v in base_polys.uniqueValues(base_polys.fields().lookupField(field_name)) if v is not None]
        if len(unique_values) == 1:
            return self._create_single_group_layer(domain, field_name, str(unique_values[0]))

        ext = domain.extent()
        max_dim = max(ext.width(), ext.height())
        spacing = max(3.0, min(12.0, max_dim / 250.0 if max_dim > 0 else 5.0))
        smooth_dist = 0  # Keep polygon boundaries unsmoothed to avoid topological overlap between neighboring clusters.

        seeds = self._boundary_sample_points(base_polys, field_name, spacing)
        if seeds.featureCount() == 0:
            seeds = processing.run("native:pointonsurface", {
                "INPUT": base_polys, "ALL_PARTS": True, "OUTPUT": "memory:"
            })["OUTPUT"]

        partition = self._partition_from_seeds(seeds, domain, field_name)
        partition = self._merge_group_polygons_back(partition, base_polys, field_name)
        partition = self._smoothed_layer(partition, field_name, smooth_dist)
        partition = self._merge_group_polygons_back(partition, base_polys, field_name)
        partition = processing.run("native:clip", {"INPUT": partition, "OVERLAY": domain, "OUTPUT": "memory:"})["OUTPUT"]
        return self._fix(partition)

    def _generic_partition(self, in_analysis, domain, field_name):
        seeds = self._make_seed_points(in_analysis)
        if seeds.featureCount() == 0:
            raise RuntimeError(self._t("no_seeds"))
        partition = self._partition_from_seeds(seeds, domain, field_name)
        # Keep line and point cluster boundaries crisp. Smoothing caused more overlap than benefit here.
        partition = processing.run("native:clip", {"INPUT": partition, "OVERLAY": domain, "OUTPUT": "memory:"})["OUTPUT"]
        return self._fix(partition)

    def _geometry_map_from_layer(self, layer):
        field_idx = layer.fields().lookupField("name")
        geom_map = {}
        for feat in layer.getFeatures():
            key = str(feat[field_idx])
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom_map[key] = QgsGeometry(geom) if key not in geom_map else geom_map[key].combine(geom)
        return geom_map

    def _source_geometry_map(self, layer, field_name):
        geom_map = {}
        if layer is None or not field_name:
            return geom_map
        field_idx = layer.fields().lookupField(field_name)
        if field_idx < 0:
            return geom_map
        for feat in layer.getFeatures():
            try:
                value = feat[field_idx]
            except Exception:
                continue
            if value is None:
                continue
            key = str(value)
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            geom_map[key] = QgsGeometry(geom) if key not in geom_map else geom_map[key].combine(geom)
        return geom_map

    def _buffered_priority_map(self, geom_map, distance):
        if not geom_map:
            return geom_map
        dist = max(float(distance or 0.0), 0.0)
        if dist <= 0.0:
            return geom_map
        buffered = {}
        for key, geom in geom_map.items():
            if geom is None or geom.isEmpty():
                continue
            try:
                b = geom.buffer(dist, 8)
            except Exception:
                b = None
            if b is None or b.isEmpty():
                buffered[key] = geom
            else:
                buffered[key] = b
        return buffered

    def _geometry_parts(self, geom):
        if geom is None or geom.isEmpty():
            return []
        try:
            if geom.isMultipart():
                parts = geom.asGeometryCollection()
                return [g for g in parts if g is not None and not g.isEmpty()]
        except Exception:
            pass
        return [geom]

    def _prune_components_without_objects(self, grouped, source_geom_map, tolerance):
        if not grouped or not source_geom_map:
            return grouped
        pruned = {}
        tol = max(float(tolerance or 0.0), 0.0)
        for key, geom in grouped.items():
            src = source_geom_map.get(key)
            if src is None or src.isEmpty():
                pruned[key] = geom
                continue
            kept = None
            for part in self._geometry_parts(geom):
                keep = False
                try:
                    if part.intersects(src):
                        keep = True
                except Exception:
                    keep = False
                if not keep and tol > 0.0:
                    try:
                        keep = part.distance(src) <= tol
                    except Exception:
                        keep = False
                if keep:
                    kept = QgsGeometry(part) if kept is None else kept.combine(part)
            if kept is not None and not kept.isEmpty():
                pruned[key] = kept
        return pruned

    def _best_cluster_for_face(self, face_geom, geom_map):
        best_key = None
        best_area = 0.0
        best_border = 0.0
        best_dist = None
        if face_geom is None or face_geom.isEmpty():
            return None
        try:
            face_boundary = face_geom.boundary()
        except Exception:
            face_boundary = None
        for key, geom in geom_map.items():
            if geom is None or geom.isEmpty():
                continue
            area = 0.0
            try:
                inter = face_geom.intersection(geom)
                if inter and not inter.isEmpty():
                    area = inter.area()
            except Exception:
                area = 0.0
            if area > best_area + 1e-9:
                best_key = key
                best_area = area
                best_border = 0.0
                best_dist = 0.0
                continue
            if best_area > 1e-9:
                continue
            border = 0.0
            if face_boundary is not None:
                try:
                    border_inter = face_boundary.intersection(geom.boundary())
                    if border_inter and not border_inter.isEmpty():
                        border = border_inter.length()
                except Exception:
                    border = 0.0
            if border > best_border + 1e-9:
                best_key = key
                best_border = border
                best_dist = 0.0
                continue
            if best_border > 1e-9:
                continue
            try:
                dist = geom.distance(face_geom)
            except Exception:
                dist = None
            if dist is not None and (best_dist is None or dist < best_dist):
                best_key = key
                best_dist = dist
        return best_key

    def _clean_overlaps(self, domain, geom_map):
        ordered = sorted(geom_map.keys(), key=lambda x: x.lower())
        assigned = None
        clean = {}
        for key in ordered:
            geom = geom_map[key]
            if assigned is not None:
                try:
                    geom = geom.difference(assigned)
                except Exception:
                    pass
            if geom is None or geom.isEmpty():
                continue
            clean[key] = geom
            assigned = geom if assigned is None else assigned.combine(geom)

        if assigned is not None:
            try:
                domain_geom = self._domain_geometry(domain)
                gaps = domain_geom.difference(assigned) if domain_geom is not None else None
            except Exception:
                gaps = None
            if gaps and not gaps.isEmpty():
                gap_layer = QgsVectorLayer(f"Polygon?crs={domain.crs().authid()}", "gaps", "memory")
                gp = gap_layer.dataProvider()
                gp.addAttributes([QgsField("id", QVariant.Int)])
                gap_layer.updateFields()
                multi = gaps.asGeometryCollection() if gaps.isMultipart() else [gaps]
                gap_feats = []
                gid = 1
                for part in multi:
                    if part is None or part.isEmpty():
                        continue
                    f = QgsFeature(gap_layer.fields())
                    f.setGeometry(part)
                    f.setAttribute("id", gid)
                    gid += 1
                    gap_feats.append(f)
                if gap_feats:
                    gp.addFeatures(gap_feats)
                    gap_layer.updateExtents()
                    for gap_part in gap_layer.getFeatures():
                        gap_geom = gap_part.geometry()
                        if gap_geom is None or gap_geom.isEmpty():
                            continue
                        best_key = self._best_cluster_for_face(gap_geom, clean)
                        if best_key:
                            clean[best_key] = clean[best_key].combine(gap_geom)
        return clean


    def _combine_layer_geometry(self, layer):
        if layer is None:
            return None
        combined = None
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            if combined is None:
                combined = QgsGeometry(geom)
            else:
                try:
                    combined = combined.combine(geom)
                except Exception:
                    try:
                        combined = QgsGeometry.unaryUnion([combined, geom])
                    except Exception:
                        pass
        return combined

    def _domain_geometry(self, domain_layer):
        domain_layer = self._fix(domain_layer)
        combined = self._combine_layer_geometry(domain_layer)
        return combined

    def _polygonize_cluster_faces(self, domain, geom_map, priority_map=None):
        domain_geom = self._domain_geometry(domain)
        if domain_geom is None or domain_geom.isEmpty() or not geom_map:
            return geom_map

        boundary_layer = QgsVectorLayer(f"LineString?crs={domain.crs().authid()}", "cluster_boundaries", "memory")
        pr = boundary_layer.dataProvider()
        feats = []

        def add_boundary(geom):
            try:
                b = geom.boundary()
            except Exception:
                b = None
            if b is None or b.isEmpty():
                return
            f = QgsFeature()
            f.setGeometry(b)
            feats.append(f)

        add_boundary(domain_geom)
        for geom in geom_map.values():
            if geom is None or geom.isEmpty():
                continue
            add_boundary(geom.intersection(domain_geom))

        if not feats:
            return geom_map
        pr.addFeatures(feats)
        boundary_layer.updateExtents()
        try:
            merged = processing.run("native:mergevectorlayers", {"LAYERS": [boundary_layer], "CRS": domain.crs(), "OUTPUT": "memory:"})["OUTPUT"]
        except Exception:
            merged = boundary_layer
        polygonized = processing.run("native:polygonize", {"INPUT": merged, "KEEP_FIELDS": False, "OUTPUT": "memory:"})["OUTPUT"]

        normalized = {k: None for k in geom_map.keys()}
        for face in polygonized.getFeatures():
            face_geom = face.geometry()
            if face_geom is None or face_geom.isEmpty():
                continue
            try:
                face_geom = face_geom.intersection(domain_geom)
            except Exception:
                pass
            if face_geom is None or face_geom.isEmpty():
                continue
            best_key = None
            if priority_map:
                best_key = self._best_cluster_for_face(face_geom, priority_map)
                if best_key not in geom_map:
                    best_key = None
            if best_key is None:
                best_key = self._best_cluster_for_face(face_geom, geom_map)
            if best_key is None:
                continue
            normalized[best_key] = QgsGeometry(face_geom) if normalized[best_key] is None else normalized[best_key].combine(face_geom)

        return {k: v for k, v in normalized.items() if v is not None and not v.isEmpty()}

    def _create_clean_output_layer(self, source_crs, features):
        mem = QgsVectorLayer(f"Polygon?crs={source_crs.authid()}", "clusters", "memory")
        pr = mem.dataProvider()
        pr.addAttributes([
            QgsField("id", QVariant.Int),
            QgsField("name", QVariant.String, len=254),
            QgsField("count", QVariant.Int),
        ])
        mem.updateFields()
        out_features = []
        for i, item in enumerate(features, start=1):
            feat = QgsFeature(mem.fields())
            feat.setGeometry(item["geometry"])
            feat.setAttribute("id", i)
            feat.setAttribute("name", item["cluster_name"])
            feat.setAttribute("count", item["count"])
            out_features.append(feat)
        pr.addFeatures(out_features)
        mem.updateExtents()
        return mem

    def _remove_existing_output(self, output_path):
        if not output_path:
            return
        for suffix in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj"]:
            p = os.path.splitext(output_path)[0] + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def _next_layer_name(self, base_name):
        existing = {layer.name() for layer in QgsProject.instance().mapLayers().values()}
        idx = 1
        while True:
            candidate = f"{base_name}_{idx:02d}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _save_or_load_result(self, layer, output_path, layer_name):
        if not output_path:
            layer.setName(self._next_layer_name(layer_name))
            QgsProject.instance().addMapLayer(layer)
            return layer
        output_path = os.path.normpath(output_path)
        if not output_path.lower().endswith(".shp"):
            output_path += ".shp"
        self._remove_existing_output(output_path)
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        options.layerName = os.path.splitext(os.path.basename(output_path))[0]
        err = QgsVectorFileWriter.writeAsVectorFormatV3(layer, output_path, QgsProject.instance().transformContext(), options)
        if err[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(self._t("saved_fail"))
        loaded = QgsVectorLayer(output_path, options.layerName, "ogr")
        if not loaded.isValid():
            raise RuntimeError(self._t("load_fail"))
        QgsProject.instance().addMapLayer(loaded)
        return loaded

    def _apply_style_and_labels(self, layer):
        field_name = "name"
        idx = layer.fields().lookupField(field_name)
        values = sorted([v for v in layer.uniqueValues(idx) if v is not None], key=lambda x: str(x))
        categories = []
        for i, value in enumerate(values):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            hue = int((i * 137.508) % 360)
            symbol.setColor(QColor.fromHsv(hue, 180, 220, 160))
            categories.append(QgsRendererCategory(value, symbol, str(value)))
        layer.setRenderer(QgsCategorizedSymbolRenderer(field_name, categories))

        text_format = QgsTextFormat()
        font = QFont("Arial", 10)
        font.setBold(True)
        text_format.setFont(font)
        text_format.setSize(10)
        text_format.setColor(QColor(0, 0, 0))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(1.0)
        buffer.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer)

        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = field_name
        label_settings.setFormat(text_format)
        label_settings.enabled = True
        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
        layer.triggerRepaint()

    def process(self):
        # Keep the accepted project baseline intact. Selection handling, optional boundary clipping,
        # and single-cluster fallback must remain stable across QGIS 3.x and 4.x.
        try:
            self._set_progress(0)
            input_layer = self.layer_combo.currentData()
            boundary_layer = self.boundary_combo.currentData()
            original_group_field = self.field_combo.currentData()
            if isinstance(original_group_field, str):
                original_group_field = original_group_field.strip()
                if not original_group_field:
                    original_group_field = None
            output_path = self.output_edit.text().strip()

            if not input_layer:
                self.push(self._t("error"), self._t("missing"), Qgis.MessageLevel.Critical, 8)
                return
            if original_group_field and input_layer.fields().lookupField(original_group_field) < 0:
                raise RuntimeError(self._t("field_not_found"))

            self._set_progress(5)
            source_crs = input_layer.crs()
            selected_mode = self.selected_only_cb.isChecked()
            selected_delete_value = None
            selected_keep_names = None

            if selected_mode:
                work_input, group_field, selected_delete_value = self._prepare_selected_mode_layer(input_layer, original_group_field)
                if original_group_field:
                    selected_keep_names = self._selected_group_values(input_layer, original_group_field)
                else:
                    selected_keep_names = {"__SELECTED__"}
            else:
                work_input = input_layer
                group_field = original_group_field

            work_crs = self._suggest_metric_crs(work_input)
            self.log(f"process start | source={input_layer.featureCount()} | selected_ids={len(input_layer.selectedFeatureIds())} | work_input={work_input.featureCount()} | selected_mode={selected_mode}")
            self._set_progress(15)

            in_work = self._reproject_if_needed(work_input, work_crs)
            in_work = self._fix(in_work)
            self.log(f"after reprojection/fix | in_work={in_work.featureCount()}")
            bnd_work = self._reproject_if_needed(boundary_layer, work_crs) if boundary_layer else None

            self._set_progress(25)
            if bnd_work:
                domain = self._boundary_domain(bnd_work)
                in_analysis = processing.run("native:extractbylocation", {
                    "INPUT": in_work,
                    "PREDICATE": [0, 1, 3, 5, 6],
                    "INTERSECT": domain,
                    "OUTPUT": "memory:"
                })["OUTPUT"]
            else:
                domain = self._extent_domain(in_work)
                in_analysis = in_work

            in_analysis = self._fix(in_analysis)
            self.log(f"analysis ready | in_analysis={in_analysis.featureCount()} | selected_only={selected_mode} | boundary={'yes' if bnd_work else 'no'}")
            if in_analysis.featureCount() == 0:
                raise RuntimeError(self._t("no_features"))

            self._set_progress(40)
            partition_field = group_field
            single_output_name = None
            if not group_field:
                partition_field = "_cg_single"
                if selected_mode and not original_group_field:
                    single_output_name = "__SELECTED__"
                else:
                    single_output_name = input_layer.name() or "output"
                count_map = {str(single_output_name): int(in_analysis.featureCount())}
                partition = self._create_single_group_layer(domain, partition_field, str(single_output_name))
                self.log(f"group count map keys={len(count_map)} | groups={sorted(list(count_map.keys()))[:20]}")
            else:
                count_map = self._build_count_map(in_analysis, group_field)
                if selected_mode and selected_delete_value is not None:
                    count_map.pop(str(selected_delete_value), None)
                    if selected_keep_names:
                        count_map = {k: v for k, v in count_map.items() if k in selected_keep_names}
                    self.log(f"selected count map filtered | kept={len(count_map)} | groups={sorted(list(count_map.keys()))[:20]}")
                else:
                    self.log(f"group count map keys={len(count_map)} | groups={sorted(list(count_map.keys()))[:20]}")

                geom_type = QgsWkbTypes.geometryType(in_analysis.wkbType())
                if geom_type == QgsWkbTypes.PolygonGeometry:
                    partition = self._polygon_partition(in_analysis, domain, group_field)
                else:
                    partition = self._generic_partition(in_analysis, domain, group_field)

            self._set_progress(78)
            source_geom_map = self._source_geometry_map(in_analysis, group_field) if group_field else {}
            if selected_mode and selected_delete_value is not None:
                source_geom_map.pop(str(selected_delete_value), None)
                if selected_keep_names:
                    source_geom_map = {k: g for k, g in source_geom_map.items() if k in selected_keep_names}
            priority_geom_map = source_geom_map
            geom_type = QgsWkbTypes.geometryType(in_analysis.wkbType())
            if geom_type != QgsWkbTypes.PolygonGeometry and source_geom_map:
                base_dist = self._default_domain_distance(in_analysis)
                priority_dist = max(0.5, min(3.0, base_dist * 0.01))
                priority_geom_map = self._buffered_priority_map(source_geom_map, priority_dist)
            grouped = {}
            for feat in partition.getFeatures():
                value = feat[partition_field]
                if value is None:
                    continue
                key = str(value)
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                grouped[key] = geom if key not in grouped else grouped[key].combine(geom)

            grouped = self._polygonize_cluster_faces(domain, grouped, priority_geom_map)
            grouped = self._clean_overlaps(domain, grouped)
            grouped = self._polygonize_cluster_faces(domain, grouped, priority_geom_map)
            tol_base = self._default_domain_distance(in_analysis)
            if geom_type == QgsWkbTypes.PolygonGeometry:
                tol = max(0.01, tol_base * 0.02)
            else:
                tol = max(0.005, tol_base * 0.008)
            grouped = self._prune_components_without_objects(grouped, source_geom_map, tol)
            grouped = self._clean_overlaps(domain, grouped)
            grouped = self._polygonize_cluster_faces(domain, grouped, priority_geom_map)
            if selected_mode:
                if selected_delete_value is not None:
                    grouped.pop(str(selected_delete_value), None)
                if selected_keep_names:
                    grouped = {k: g for k, g in grouped.items() if k in selected_keep_names}
                self.log(f"selected grouped filter active | kept_grouped={len(grouped)}")
            ordered = sorted(grouped.keys(), key=lambda x: x.lower())
            self._set_progress(88)
            output_features = []
            for key in ordered:
                output_name = key
                if selected_mode and not original_group_field and key == "__SELECTED__":
                    output_name = input_layer.name()
                output_features.append({
                    "cluster_name": output_name,
                    "count": int(count_map.get(key, 0)),
                    "geometry": grouped[key]
                })

            clean = self._create_clean_output_layer(work_crs, output_features)
            clean = self._fix(clean)
            if clean.crs().authid() != source_crs.authid():
                clean = processing.run("native:reprojectlayer", {
                    "INPUT": clean, "TARGET_CRS": source_crs, "OUTPUT": "memory:"
                })["OUTPUT"]

            self._set_progress(96)
            layer_name = f"Cluster_{input_layer.name()}"
            result_layer = self._save_or_load_result(clean, output_path, layer_name)
            self._apply_style_and_labels(result_layer)
            self._set_progress(100)
            self.push(self._t("success"), self._t("done"), Qgis.MessageLevel.Success, 8)
            try:
                self.dlg.accept()
            except Exception:
                pass
        except Exception as e:
            self.log(traceback.format_exc(), Qgis.MessageLevel.Critical)
            self.push(self._t("error"), str(e), Qgis.MessageLevel.Critical, 12)
            self._set_progress(0)
