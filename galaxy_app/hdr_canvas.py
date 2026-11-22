"""Accumulate stellar light in float on the GPU, then compress highlights once."""
from __future__ import annotations
import logging
import numpy as np
from vispy import scene,gloo

VERTEX='''
attribute vec2 a_position;
varying vec2 v_uv;
void main() { v_uv=(a_position+1.0)*0.5; gl_Position=vec4(a_position,0.0,1.0); }
'''
FRAGMENT='''
uniform sampler2D u_light;
uniform float u_exposure;
uniform float u_detail;
uniform float u_reference;
varying vec2 v_uv;
void main() {
    vec3 background=vec3(2.0,3.0,8.0)/255.0;
    vec3 light=max(texture2D(u_light,v_uv).rgb-background,vec3(0.0));
    float peak=max(max(light.r,light.g),light.b);
    float value=1.0-exp(-log(1.0+peak*max(u_exposure,0.01))*(0.42/max(u_detail,0.3)));
    value=pow(value,0.72);
    if (u_reference>0.5) { value=pow(1.0-exp(-peak*u_exposure),0.85); }
    vec3 colour=light/max(peak,0.00000001)*value+background;
    gl_FragColor=vec4(colour,1.0);
}
'''

class LightCanvas(scene.SceneCanvas):
    def __init__(self,*args,**kwargs):
        self._light_buffer=None;self._light_size=None;self._tone_program=None
        self.protect_highlights=True;self.exposure=1.25;self.core_detail=1.
        self.hdr_available=True
        self.reference_mode=False
        super().__init__(*args,**kwargs)

    def _draw_scene(self,bgcolor=None):
        if not self.protect_highlights or not self.hdr_available:
            return super()._draw_scene(bgcolor)
        self.set_current()
        if self._fb_stack:
            framebuffer,offset,logical_size=self._fb_stack[-1]
            h,w=framebuffer.color_buffer.shape[:2]
        else:
            w,h=self.physical_size;offset=(0,0);logical_size=self.size
        if w<1 or h<1:return
        try:
            if self._light_size!=(w,h):
                if self._light_buffer is not None:self._light_buffer.delete()
                texture=gloo.Texture2D(np.zeros((h,w,4),np.float32),
                                       internalformat='rgba16f',interpolation='nearest')
                self._light_buffer=gloo.FrameBuffer(texture,gloo.RenderBuffer((h,w)))
                self._light_size=(w,h)
            if self._tone_program is None:
                self._tone_program=gloo.Program(VERTEX,FRAGMENT)
                self._tone_program['a_position']=np.array([[-1,-1],[1,-1],[-1,1],[1,1]],np.float32)
            self.push_fbo(self._light_buffer,offset,logical_size)
            try:super()._draw_scene(bgcolor)
            finally:self.pop_fbo()
            self._tone_program['u_light']=self._light_buffer.color_buffer
            self._tone_program['u_exposure']=float(self.exposure)
            self._tone_program['u_detail']=float(self.core_detail)
            self._tone_program['u_reference']=1. if self.reference_mode else 0.
            gloo.set_state(blend=False,depth_test=False,scissor_test=False,cull_face=False)
            gloo.set_viewport(0,0,w,h)
            self._tone_program.draw('triangle_strip')
        except Exception:
            self.hdr_available=False
            logging.getLogger(__name__).exception('Floating-point display unavailable; using the compatibility view')
            super()._draw_scene(bgcolor)
