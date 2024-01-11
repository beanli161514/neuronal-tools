import numpy as np
import napari
import json
import os
from magicgui import magicgui, widgets
from ntools.read_ims import Image
from tifffile import imwrite


class SimpleViewer:
    def __init__(self):
        self.viewer = napari.Viewer(ndisplay=3,title='instance annotator')
        self.image_layer = self.viewer.add_image(np.zeros((64, 64, 64), dtype=np.uint16),name='image')
        self.goal_layer = self.viewer.add_points(ndim=3,face_color='red',size=2,edge_color='black',shading='spherical',name='goal')
        self.add_callback()
        self.image = None
        napari.run()

    def add_callback(self):
        self.viewer.bind_key('f', self.refresh)
        self.image_layer.mouse_double_click_callbacks.append(self.on_double_click)

        self.button0 = widgets.PushButton(text="refresh")
        self.button0.clicked.connect(self.refresh)
        self.button1 = widgets.PushButton(text="level up")
        self.button1.clicked.connect(self.level_up)
        self.button2 = widgets.PushButton(text="level down")
        self.button2.clicked.connect(self.level_down)
        self.button3 = widgets.PushButton(text="save image")
        self.button3.clicked.connect(self.save_image)
        self.image_path = widgets.FileEdit(label="image_path")
        self.save_dir = widgets.FileEdit(label="save dir",mode='d')
        self.size = widgets.LineEdit(label="block size", value=128)
        self.x = widgets.LineEdit(label="x coordinate", value=5280)
        self.y = widgets.LineEdit(label="y coordinate",value=4000)
        self.z = widgets.LineEdit(label="z coordinate",value=8480)
        self.level = widgets.LineEdit(label="level",value=0)
        self.level_info = widgets.TextEdit(label='level info')
        self.container = widgets.Container(widgets=[self.image_path, self.save_dir,self.size, self.x, self.y, self.z, self.level, self.level_info, self.button3, self.button1, self.button2 ,self.button0])
        self.viewer.window.add_dock_widget(self.container, area='right')


    def refresh(self):
        if self.image is None:
            self.image = Image(self.image_path.value)
        roi = [int(float(self.x.value)-int(self.size.value)//2) ,int(float(self.y.value)-int(self.size.value)//2), int(float(self.z.value)-int(self.size.value)//2),int(self.size.value), int(self.size.value), int(self.size.value)]
        print(roi)
        self.image_layer.data = self.image.from_roi(roi, int(self.level.value))
        self.image_layer.translate = roi[:3]
        camera_state = self.viewer.camera.angles
        self.viewer.reset_view()
        self.viewer.camera.angles = camera_state
        self.viewer.layers.selection.active = self.image_layer
        self.image_layer.reset_contrast_limits()
        info = "\n".join(f"{key}: {value}" for key, value in self.image.info[int(self.level.value)].items())
        self.level_info.value = info


    def level_down(self):
        cx = int(float(self.x.value))
        cy = int(float(self.y.value))
        cz = int(float(self.z.value))
        cl = int(self.level.value)
        if cl==0:
            return
        tl = cl-1
        c_spacing = self.image.info[cl]['spacing']
        t_spacing = self.image.info[tl]['spacing']
        scale = [i/j for i,j in zip(c_spacing,t_spacing)]
        self.level.value = tl
        tx = int(cx*scale[0]) 
        ty = int(cy*scale[1]) 
        tz = int(cz*scale[2]) 
        self.x.value = tx
        self.y.value = ty
        self.z.value = tz
        self.goal_layer.data = [tx,ty,tz]
        self.refresh()


    def level_up(self):
        cx = int(float(self.x.value))
        cy = int(float(self.y.value))
        cz = int(float(self.z.value))
        cl = int(self.level.value)
        if cl==7:
            return
        tl = cl+1
        c_spacing = self.image.info[cl]['spacing']
        t_spacing = self.image.info[tl]['spacing']
        scale = [i/j for i,j in zip(c_spacing,t_spacing)]
        self.level.value = tl
        tx = int(cx*scale[0]) 
        ty = int(cy*scale[1]) 
        tz = int(cz*scale[2]) 
        self.x.value = tx
        self.y.value = ty
        self.z.value = tz
        self.goal_layer.data = [tx,ty,tz]
        self.refresh()


    def on_double_click(self,layer,event):
        #based on ray casting
        near_point, far_point = layer.get_ray_intersections(
            event.position,
            event.view_direction,
            event.dims_displayed
        )
        sample_ray = far_point - near_point
        length_sample_vector = np.linalg.norm(sample_ray)
        increment_vector = sample_ray / (2 * length_sample_vector)
        n_iterations = int(2 * length_sample_vector)
        bbox = np.array([
            [0, layer.data.shape[0]-1],
            [0, layer.data.shape[1]-1],
            [0, layer.data.shape[2]-1]
        ])
        sample_points = []
        values = []
        for i in range(n_iterations):
            sample_point = np.asarray(near_point + i * increment_vector, dtype=int)
            sample_point = self.clamp_point_to_bbox(sample_point, bbox)
            value = layer.data[sample_point[0], sample_point[1], sample_point[2]]
            sample_points.append(sample_point)
            values.append(value)
        max_point_index = values.index(max(values))
        max_point = sample_points[max_point_index]
        max_point = [i+j for i,j in zip(max_point,self.image_layer.translate)]
        print('Put point at: ', max_point)
        if(event.button==1):
            self.goal_layer.data = max_point
            self.x.value = max_point[0]
            self.y.value = max_point[1]
            self.z.value = max_point[2]
            self.refresh()


    def clamp_point_to_bbox(self, point: np.ndarray, bbox: np.ndarray):
        clamped_point = np.clip(point, bbox[:, 0], bbox[:, 1])
        return clamped_point


    def save_image(self, viewer):
        # image_name = filedialog.asksaveasfilename()
        all_files = os.listdir(self.save_dir.value)

        tif_files = [file for file in all_files if file.endswith('.tif')]
        next_image_number = len(tif_files)+1
        image_name = f'img_{next_image_number}.tif'
        image_name = os.path.join(self.save_dir.value, image_name)

        image = self.image_layer.data
        imwrite(image_name,image)

        print(image_name+' saved')


if __name__ == '__main__':
    s = SimpleViewer()
