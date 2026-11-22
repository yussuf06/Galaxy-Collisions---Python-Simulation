"""Repeatable, freely evolved encounters inspired by observed galaxy shapes.

These are educational starting conditions and viewing suggestions, not fitted
models of the named NASA observations. No target shape is imposed on particles.
"""
from copy import deepcopy

SHAPES=(
    dict(id='heart',name='Heart / القلب',pair='Inspired by the Antennae galaxies',
         description='Two similar spirals and curved tidal material. Shape changes with time and viewing angle.',
         config=dict(seed=735128,impact=1.15,speed=.85,massratio=1.,inclination=15.,spin=1,
                     isolated=False,morphology_b='spiral',aligned_disks=True),
         time=9.,azimuth=25.,elevation=74.,palette='aurora'),
    dict(id='rose',name='Rose / الوردة',pair='Inspired by Arp 273',
         description='A large spiral interacting with a smaller companion; look for swept and distorted arms.',
         config=dict(seed=735128,impact=1.4,speed=.95,massratio=.6,inclination=35.,spin=1,
                     isolated=False,morphology_b='spiral',aligned_disks=True),
         time=9.,azimuth=-35.,elevation=65.,palette='violet'),
    dict(id='mice',name='Mice / الفئران',pair='Inspired by NGC 4676',
         description='Two passing spirals pull out elongated stellar tails. Rotate to follow each tail.',
         config=dict(seed=735128,impact=1.6,speed=1.2,massratio=1.,inclination=10.,spin=1,
                     isolated=False,morphology_b='spiral',aligned_disks=True),
         time=12.,azimuth=100.,elevation=55.,palette='ocean'),
    dict(id='penguin',name='Penguin / البطريق',pair='Inspired by Arp 142',
         description='A spiral meets a round stellar companion. The round galaxy represents the Egg.',
         config=dict(seed=735128,impact=1.4,speed=1.15,massratio=1.,inclination=0.,spin=1,
                     isolated=False,morphology_b='spheroid',aligned_disks=True),
         time=7.5,azimuth=-40.,elevation=55.,palette='ocean'),
)

def get_shape(ident):
    for shape in SHAPES:
        if shape['id']==ident:return deepcopy(shape)
    raise ValueError('Unknown shape preset')

def shape_config(requested,ident):
    shape=get_shape(ident)
    return {**requested,**shape['config'],'shape_id':ident}
