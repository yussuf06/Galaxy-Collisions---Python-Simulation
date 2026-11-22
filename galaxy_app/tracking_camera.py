"""Small, view-only tracking controller; never changes a simulation frame."""
import math
import numpy as np


class TrackingCamera:
    def __init__(self):
        self.reset(np.zeros(3), 42.)

    def reset(self, center, distance):
        self.center=np.asarray(center,dtype=float).copy()
        self.distance=float(distance)
        self.target_center=self.center.copy();self.target_distance=self.distance
        self.settled=True

    def retarget(self, positions, centers, aspect):
        points=np.asarray(positions)
        if not len(points):return
        self.target_center=np.asarray(centers,dtype=float).mean(axis=0)
        sample=points[::max(1,len(points)//4096)]
        radius=float(np.quantile(np.linalg.norm(sample-self.target_center,axis=1),.995))
        # A sphere remains in frame at every orbit angle, with room for tails.
        self.target_distance=max(12.,radius/math.sin(math.radians(22.5))*1.12/min(1.,max(.25,aspect)))
        self.settled=(np.linalg.norm(self.target_center-self.center)<.005 and
                      abs(self.target_distance-self.distance)<.01)

    def advance(self, dt):
        dt=float(np.clip(dt,0.,.1))
        if self.settled:return self.center,self.distance
        self.center+=(self.target_center-self.center)*(-math.expm1(-6.*dt))
        rate=7. if self.target_distance>self.distance else 2.5
        self.distance+=(self.target_distance-self.distance)*(-math.expm1(-rate*dt))
        if np.linalg.norm(self.target_center-self.center)<.005:
            self.center=self.target_center.copy()
        if abs(self.target_distance-self.distance)<max(.01,self.target_distance*.0002):
            self.distance=self.target_distance
        self.settled=(np.array_equal(self.center,self.target_center) and self.distance==self.target_distance)
        return self.center,self.distance
