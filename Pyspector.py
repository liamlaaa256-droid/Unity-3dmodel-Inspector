# unity_inspector_flycam.py
# Requires: pip install PyQt5 PyOpenGL trimesh Pillow UnityPy numpy

import sys
import os
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *
import trimesh
from PIL import Image
import UnityPy

# ---------------- Model Object ----------------
class ModelObject:
    def __init__(self, mesh=None, texture=None, name="", raw_obj=None):
        self.mesh = mesh
        self.texture_image = texture  # PIL Image
        self.texture_id = None
        self.name = name
        self.raw_obj = raw_obj
        self.position = np.array([0.0,0.0,0.0])
        self.rotation = np.array([0.0,0.0,0.0])
        self.scale = np.array([1.0,1.0,1.0])

    def create_gl_texture(self):
        if self.texture_image is None:
            return
        try:
            img = self.texture_image.convert("RGBA")
            img_data = np.array(img, dtype=np.uint8)
            if self.texture_id is None:
                self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,img.width,img.height,0,GL_RGBA,GL_UNSIGNED_BYTE,img_data)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glBindTexture(GL_TEXTURE_2D,0)
        except Exception as e:
            print(f"Failed to create GL texture for {self.name}: {e}")
            self.texture_id = None

# ---------------- OpenGL Viewport ----------------
class GLViewport(QOpenGLWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.models = []

        # Camera
        self.cam_pos = np.array([0.0,0.0,5.0])
        self.cam_rot = np.array([0.0,0.0])  # yaw, pitch
        self.keys = set()
        self.last_mouse_pos = None
        self.right_button_held = False

        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glClearColor(0.12,0.12,0.12,1.0)
        for obj in self.models:
            obj.create_gl_texture()

    def resizeGL(self,w,h):
        glViewport(0,0,w,h)
        self.width = max(1,w)
        self.height = max(1,h)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(60.0, self.width/self.height,0.1,1000.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glRotatef(-self.cam_rot[1],1,0,0)
        glRotatef(-self.cam_rot[0],0,1,0)
        glTranslatef(-self.cam_pos[0],-self.cam_pos[1],-self.cam_pos[2])

        for obj in self.models:
            if obj.mesh is None:
                continue
            glPushMatrix()
            glTranslatef(*obj.position)
            glRotatef(obj.rotation[0],1,0,0)
            glRotatef(obj.rotation[1],0,1,0)
            glRotatef(obj.rotation[2],0,0,1)
            glScalef(*obj.scale)

            try:
                vertices = np.array(obj.mesh.vertices)
                faces = np.array(obj.mesh.faces, dtype=np.int32)
            except Exception as e:
                glPopMatrix()
                continue

            uvs = None
            if hasattr(obj.mesh.visual,'uv') and obj.mesh.visual.uv is not None:
                try:
                    uvs = np.array(obj.mesh.visual.uv)
                except:
                    uvs = None

            if obj.texture_id:
                glBindTexture(GL_TEXTURE_2D,obj.texture_id)
            else:
                glBindTexture(GL_TEXTURE_2D,0)

            glBegin(GL_TRIANGLES)
            for f in faces:
                for idx in f:
                    if uvs is not None and idx < len(uvs):
                        glTexCoord2f(uvs[idx][0], 1.0 - uvs[idx][1])
                    glVertex3f(vertices[idx][0], vertices[idx][1], vertices[idx][2])
            glEnd()
            glBindTexture(GL_TEXTURE_2D,0)
            glPopMatrix()

        self.process_input()

    # ---------------- Camera movement ----------------
    def process_input(self):
        speed = 0.12
        yaw_rad = np.radians(self.cam_rot[0])
        forward = np.array([np.sin(yaw_rad),0,np.cos(yaw_rad)])
        right = np.array([np.cos(yaw_rad),0,-np.sin(yaw_rad)])
        up = np.array([0,1,0])

        if Qt.Key_W in self.keys: self.cam_pos += forward * speed
        if Qt.Key_S in self.keys: self.cam_pos -= forward * speed
        if Qt.Key_A in self.keys: self.cam_pos -= right * speed
        if Qt.Key_D in self.keys: self.cam_pos += right * speed
        if Qt.Key_Space in self.keys: self.cam_pos += up * speed
        if Qt.Key_Shift in self.keys: self.cam_pos -= up * speed

    def keyPressEvent(self,event):
        self.keys.add(event.key())

    def keyReleaseEvent(self,event):
        if event.key() in self.keys:
            self.keys.remove(event.key())

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.right_button_held = True
        self.last_mouse_pos = event.pos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.right_button_held = False
        self.last_mouse_pos = None

    def mouseMoveEvent(self,event):
        if not self.right_button_held:
            self.last_mouse_pos = event.pos()
            return
        if self.last_mouse_pos is None:
            self.last_mouse_pos = event.pos()
            return
        dx = event.x() - self.last_mouse_pos.x()
        dy = event.y() - self.last_mouse_pos.y()
        self.last_mouse_pos = event.pos()
        self.cam_rot[0] += dx * 0.2
        self.cam_rot[1] += dy * 0.2
        self.cam_rot[1] = np.clip(self.cam_rot[1], -89, 89)

# ---------------- Main Window ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unity Asset Inspector (permissioned use only)")
        self.setGeometry(80,80,1400,800)

        self.asset_tree = QTreeWidget()
        self.asset_tree.setHeaderLabels(["Assets"])
        self.asset_tree.itemClicked.connect(self.on_item_clicked)

        self.load_model_btn = QPushButton("Load 3D Model (OBJ/GLTF/FBX)")
        self.load_model_btn.clicked.connect(self.load_model_file)

        self.load_unity_btn = QPushButton("Load Unity Package (.assets/.bundle)")
        self.load_unity_btn.clicked.connect(self.load_unity)

        self.extract_all_btn = QPushButton("Extract All to Folder")
        self.extract_all_btn.clicked.connect(self.extract_all)

        self.export_btn = QPushButton("Export Selected Model")
        self.export_btn.clicked.connect(self.export_model)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.asset_tree)
        left_layout.addWidget(self.load_model_btn)
        left_layout.addWidget(self.load_unity_btn)
        left_layout.addWidget(self.extract_all_btn)
        left_layout.addWidget(self.export_btn)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        self.viewport = GLViewport()

        main_layout = QHBoxLayout()
        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(self.viewport, 7)
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.models = []

    def add_model_to_tree(self, model_obj):
        item = QTreeWidgetItem([model_obj.name])
        self.asset_tree.addTopLevelItem(item)
        self.models.append(model_obj)
        self.viewport.models = self.models

    # ---------------- Load generic models ----------------
    def load_model_file(self):
        file_path,_ = QFileDialog.getOpenFileName(self,"Open Model File","","3D Models (*.obj *.fbx *.glb *.gltf)")
        if not file_path:
            return
        try:
            mesh = trimesh.load(file_path, force='mesh')
            texture = None
            if hasattr(mesh.visual, 'material') and hasattr(mesh.visual.material, 'image'):
                texture = mesh.visual.material.image
            name = os.path.basename(file_path)
            model_obj = ModelObject(mesh=mesh, texture=texture, name=name)
            self.add_model_to_tree(model_obj)
            try:
                self.viewport.makeCurrent()
                model_obj.create_gl_texture()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self,"Load Error", f"Failed to load model:\n{e}")

    # ---------------- Load Unity package ----------------
    def load_unity(self):
        file_path,_ = QFileDialog.getOpenFileName(self,"Open Unity Package File","","Unity Assets (*.assets *.bundle *.unity3d)")
        if not file_path:
            return
        try:
            env = UnityPy.load(file_path)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"UnityPy failed to open the file:\n{e}\nIt may be encrypted or invalid.")
            return

        texture_map = {}
        mesh_entries = []

        for obj in env.objects:
            typ = obj.type.name
            try:
                if typ == "Texture2D":
                    tex = obj.read()
                    img = tex.image
                    tname = tex.name if getattr(tex,"name",None) else f"texture_{obj.path_id}"
                    texture_map[tname] = img
                    model_obj = ModelObject(mesh=None, texture=img, name=f"[T] {tname}", raw_obj=obj)
                    self.add_model_to_tree(model_obj)
                elif typ == "Mesh":
                    mesh_obj = obj.read()
                    verts = getattr(mesh_obj, "vertices", None)
                    tris = None
                    if hasattr(mesh_obj, "triangles") and mesh_obj.triangles:
                        flat = mesh_obj.triangles
                        tris = [flat[i:i+3] for i in range(0, len(flat), 3)]
                    elif hasattr(mesh_obj, "faces") and mesh_obj.faces:
                        tris = mesh_obj.faces
                    if verts is not None and tris:
                        try:
                            tm = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(tris), process=False)
                            name = getattr(mesh_obj, "name", None) or f"mesh_{obj.path_id}"
                            mesh_entries.append((name, tm, obj))
                        except Exception as e:
                            print("Failed to convert unity mesh to trimesh:", e)
                            mesh_entries.append((f"mesh_{obj.path_id}", None, obj))
                elif typ in ("TextAsset", "MonoBehaviour"):
                    text = obj.read()
                    name = getattr(text, "name", None) or f"text_{obj.path_id}"
                    model_obj = ModelObject(mesh=None, texture=None, name=f"[S] {name}", raw_obj=obj)
                    self.add_model_to_tree(model_obj)
            except Exception as e:
                print(f"Skipping object {obj.path_id} ({typ}) due to error: {e}")

        for name, tm, unity_obj in mesh_entries:
            assigned_texture = None
            for tname, img in texture_map.items():
                if tname.lower() in name.lower() or name.lower() in tname.lower():
                    assigned_texture = img
                    break
            model_obj = ModelObject(mesh=tm, texture=assigned_texture, name=f"[M] {name}", raw_obj=unity_obj)
            self.add_model_to_tree(model_obj)
            try:
                self.viewport.makeCurrent()
                model_obj.create_gl_texture()
            except Exception:
                pass

        QMessageBox.information(self, "Loaded", f"Loaded Unity package: {len(texture_map)} textures, {len(mesh_entries)} meshes (best-effort mapping).")

    # ---------------- Extract All ----------------
    def extract_all(self):
        out_dir = QFileDialog.getExistingDirectory(self, "Select folder to extract all assets into")
        if not out_dir:
            return
        for i, m in enumerate(self.models):
            try:
                if m.mesh is None and m.texture_image is not None:
                    name = m.name.replace("[T] ", "").replace("[S] ", "").replace("[M] ", "")
                    path = os.path.join(out_dir, f"{name}.png")
                    m.texture_image.save(path)
                if m.mesh is not None:
                    if isinstance(m.mesh, trimesh.Trimesh):
                        fname = f"{m.name.replace('[M] ','').replace(' ','_')}.obj"
                        path = os.path.join(out_dir, fname)
                        m.mesh.export(path)
                if m.raw_obj is not None:
                    try:
                        typ = m.raw_obj.type.name
                        if typ in ("TextAsset", "MonoBehaviour"):
                            data = m.raw_obj.read()
                            content = getattr(data, "script", None) or getattr(data, "source", None) or getattr(data, "m_Script", None)
                            if content is None:
                                content = getattr(data, "serialized_data", None) or getattr(data, "m_Script", None) or ""
                            fname = f"{m.name.replace('[S] ','')}.txt"
                            with open(os.path.join(out_dir, fname), "w", encoding="utf-8", errors="ignore") as f:
                                f.write(str(content))
                    except Exception as e:
                        print("Failed extracting raw unity text asset:", e)
            except Exception as exc:
                print("Error extracting asset:", exc)
        QMessageBox.information(self, "Extracted", f"Assets extracted to: {out_dir}")

    # ---------------- Export selected model ----------------
    def export_model(self):
        item = self.asset_tree.currentItem()
        if not item:
            QMessageBox.warning(self, "Export", "No asset selected.")
            return
        idx = self.asset_tree.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self.models):
            QMessageBox.warning(self, "Export", "Invalid selection.")
            return
        m = self.models[idx]
        if m.mesh is None:
            QMessageBox.warning(self, "Export", "Selected item has no mesh to export.")
            return
        save_path,_ = QFileDialog.getSaveFileName(self, "Export Mesh", f"{m.name}.obj", "OBJ Files (*.obj)")
        if save_path:
            try:
                if isinstance(m.mesh, trimesh.Trimesh):
                    m.mesh.export(save_path)
                    QMessageBox.information(self, "Exported", f"Exported to {save_path}")
                else:
                    QMessageBox.warning(self, "Export", "Mesh type not supported for direct export.")
            except Exception as e:
                QMessageBox.warning(self, "Export", f"Failed to export: {e}")

    def on_item_clicked(self, item, col):
        idx = self.asset_tree.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self.models):
            return
        selected = self.models[idx]
        self.viewport.cam_pos = np.array([0.0, 0.0, 5.0])
        try:
            if selected.mesh is not None and isinstance(selected.mesh, trimesh.Trimesh):
                centroid = selected.mesh.centroid
                self.viewport.cam_pos = np.array([centroid[0], centroid[1], centroid[2] + max(selected.mesh.extents)*1.5])
        except Exception:
            pass
        try:
            self.viewport.makeCurrent()
            selected.create_gl_texture()
        except Exception:
            pass

# ---------------- Run ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
