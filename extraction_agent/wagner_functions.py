### Python 3.10.13
# ── Future compatibility ───────────────────────────────────────────────────────
from __future__ import annotations 

# ── Basic libraries ──────────────────────────────────────────────
import numpy as np    # numerical arrays and math operations
import pandas as pd   # tabular data manipulation (DataFrames)


# ── Formatting libraries ──────────────────────────────────────────────────────────
import asyncio      
import json           
import os             
import pickle        
import re           
import sys            
from typing import (  
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Type,
)

# ── AI / LLM ─────────────────────────────────────────────────────
from openai import AsyncOpenAI                          # async OpenAI API client
from pydantic import BaseModel, Field, create_model     # data validation and schema definition
from pydantic_ai import Agent                           # high-level LLM agent abstraction
from pydantic_ai.models.openai import OpenAIChatModel   # pydantic-ai wrapper for OpenAI chat models
from pydantic_ai.providers.openai import OpenAIProvider # provider config (base URL, auth) for OpenAI
from enum import Enum

## Read in data extracted manually from Wagner Book
manual_extracted_data_df = pd.read_csv("./manual_extracted_wagner_data.csv", index_col=0)

def parse_text_inputs(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    sections = re.split(r'-{3,}INPUT FOR (.+?)-{3,}', content)
    
    text_inputs = {}
    # sections[0] is empty, then alternates: name, content, name, content...
    for i in range(1, len(sections), 2):
        key = sections[i].strip().replace(' ', '_')
        value = sections[i + 1].strip() if i + 1 < len(sections) else ''
        text_inputs[key] = value
    
    return text_inputs


def _meas(m):
    if m is None:
        return None
    return {'exmin': m.extreme_min, 'min': m.min, 'max': m.max, 'exmax': m.extreme_max, 'unit': m.unit}

def result_to_row(result):
    c   = result.get('core')
    st  = result.get('stem_morphology')
    lf  = result.get('leaf_morphology')
    ll  = result.get('leaflet_morphology')
    jl  = result.get('juvenile_leaf_morphology')
    lft = result.get('life_form')
    rp  = result.get('reproductive_morphology')
    ds  = result.get('distribution')
    inf = result.get('inflorescence_morphology')
    fl  = result.get('outer_flower_morphology')
    fr  = result.get('fruit_morphology')
    cap = result.get('Inflorescence_Specific')
    inv = result.get('bract_involucre_morphology')
    li  = result.get('leaf_indumentum')
    br  = result.get('bract_involucre_morphology')

    fam = c.family  if c else None
    gen = c.genus   if c else None
    sp  = c.species if c else None

    def enums(obj, attr):
        v = getattr(obj, attr, None) if obj else None
        return [x.value for x in v] if v else []

    def dim_l(obj, attr):
        d = getattr(obj, attr, None) if obj else None
        return _meas(d.length if d else None)

    def dim_w(obj, attr):
        d = getattr(obj, attr, None) if obj else None
        return _meas(d.width if d else None)

    def meas(obj, attr):
        return _meas(getattr(obj, attr, None) if obj else None)

    return {
        'family':                           fam,
        'genus':                            gen,
        'species':                          sp,
        'common_name':                      c.common_name if c else None,
        'wagner_pg_number':                 c.wagner_pg_number if c else None,
        'description':                      c.description.value if c and c.description else None,
        'infraspecific_epithet':            c.infraspecific_epithet if c else None,
        'stem_hair_type':                   enums(st, 'stem_hair_type'),
        'phyllotaxy_type':                  enums(lf, 'phyllotaxy_type'),
        'breeding_type':                    enums(lft, 'breeding_type'),
        'inflorescence_type':               enums(inf, 'inflorescence_type'),
        'ray_color':                        cap.ray_color if cap else None,
        'floret_color':                     cap.floret_color if cap else None,
        'spathe_color':                     cap.spathe_color if cap else None,
        'perianth_outer_color':             fl.perianth_outer_color if fl else None,
        'perianth_inner_color':             fl.perianth_inner_color if fl else None,
        'perianth_color':                   fl.perianth_color if fl else None,
        'labellum_color':                   fl.labellum_color if fl else None,
        'corolla_type':                     enums(fl, 'corolla_type'),
        'staminate_corolla_type':           None,
        'pistillate_corolla_type':          None,
        'corolla_color':                    fl.corolla_color if fl else None,
        'fruit_type':                       enums(fr, 'fruit_type'),
        'ploidy':                           rp.ploidy if rp else [],
        'chromosome_number':                rp.chromosome_number if rp else [],
        'average_chromosome_number':        None,
        'origin':                           enums(ds, 'origin'),
        'status':                           enums(ds, 'status'),
        'life_form_type':                   enums(lft, 'life_form_type'),
        'leaf_type':                        enums(lf, 'leaf_type'),
        'leaf_margin_type':                 enums(lf, 'leaf_margin_type'),
        'leaf_shape_type':                  enums(lf, 'leaf_shape_type'),
        'juvenile_leaf_type':               enums(jl, 'juvenile_leaf_type'),
        'juvenile_leaf_margin_type':        enums(jl, 'juvenile_leaf_margin_type'),
        'juvenile_leaf_shape_type':         enums(jl, 'juvenile_leaf_shape_type'),
        'leaflets_leaf_type':               enums(ll, 'leaflets_leaf_type'),
        'leaflets_leaf_margin_type':        enums(ll, 'leaflets_leaf_margin_type'),
        'leaflets_leaf_shape_type':         enums(ll, 'leaflets_leaf_shape_type'),
        'leaf_hair_type':                   enums(li, 'leaf_hair_type'),
        'leaf_hair_upper_type':             enums(li, 'upper_leaf_hair_type'),
        'leaf_hair_lower_type':             enums(li, 'lower_leaf_hair_type'),
        'juvenile_leaf_hair_type':          enums(jl, 'juvenile_leaf_hair_type'),
        'island_type':                      enums(ds, 'island_type'),
        'hawaiian_name':                    set(c.hawaiian_name) if c and c.hawaiian_name else set(),
        'stem_height':                      meas(st, 'stem_height'),
        'leaf_length':                      dim_l(lf, 'leaf_dimensions'),
        'leaf_width':                       dim_w(lf, 'leaf_dimensions'),
        'juvenile_leaf_length':             dim_l(jl, 'juvenile_leaf_dimensions'),
        'juvenile_leaf_width':              dim_w(jl, 'juvenile_leaf_dimensions'),
        'leaflets_leaf_length':             dim_l(ll, 'leaflets_leaf_dimensions'),
        'leaflets_leaf_width':              dim_w(ll, 'leaflets_leaf_dimensions'),
        'petioles':                         meas(lf, 'petiole_length'),
        'staminate_inflorescence_length':   dim_l(inf, 'staminate_inflorescence_dimensions'),
        'staminate_inflorescence_width':    dim_w(inf, 'staminate_inflorescence_dimensions'),
        'pistillate_inflorescence_length':  dim_l(inf, 'pistillate_inflorescence_dimensions'),
        'pistillate_inflorescence_width':   dim_w(inf, 'pistillate_inflorescence_dimensions'),
        'inflorescence_flower_length':      dim_l(inf, 'inflorescence_dimensions'),
        'inflorescence_flower_width':       dim_w(inf, 'inflorescence_dimensions'),
        'flower_length':                    dim_l(fl, 'flower_dimensions'),
        'flower_width':                     dim_w(fl, 'flower_dimensions'),
        'rachis_length':                    meas(inf, 'rachis_length'),
        'rachis_diameter':                  meas(inf, 'rachis_diameter'),
        'head_length':                      meas(cap, 'head_length'),
        'head_diameter':                    meas(cap, 'head_diameter'),
        'bur_length':                       meas(fr, 'bur_length'),
        'tepal_length':                     meas(fl, 'tepal_length'),
        'staminate_tepal_length':           meas(fl, 'staminate_tepal_length'),
        'pistillate_tepal_length':          meas(fl, 'pistillate_tepal_length'),
        'ray_length':                       dim_l(cap, 'ray_dimensions'),
        'ray_width':                        dim_w(cap, 'ray_dimensions'),
        'florets_length':                   meas(cap, 'florets_length'),
        'involucre_length':                 dim_l(inv, 'involucre_dimensions'),
        'involucre_width':                  dim_w(inv, 'involucre_dimensions'),
        'staminate_involucre_length':       meas(inv, 'staminate_involucre_length'),
        'pistilate_involucre_length':       meas(inv, 'pistillate_involucre_length'),
        'bract_length':                     dim_l(br, 'bract_dimensions'),
        'bract_width':                      dim_w(br, 'bract_dimensions'),
        'bract_lower_length':               meas(br, 'bract_lower_length'),
        'bract_outer_length':               meas(br, 'bract_outer_length'),
        'bracteoles_length':                dim_l(br, 'bracteoles_dimensions'),
        'bracteoles_width':                 dim_w(br, 'bracteoles_dimensions'),
        'pedicel_length':                   dim_l(inf, 'pedicel_dimensions'),
        'pedicel_width':                    dim_w(inf, 'pedicel_dimensions'),
        'pistillate_pedicel_length':        dim_l(inf, 'pistillate_pedicel_dimensions'),
        'hypanthium_length':                dim_l(inf, 'hypanthium_dimensions'),
        'hypanthium_width':                 dim_w(inf, 'hypanthium_dimensions'),
        'peduncle_length':                  dim_l(inf, 'peduncle_dimensions'),
        'peduncle_width':                   dim_w(inf, 'peduncle_dimensions'),
        'spathe_length':                    dim_l(cap, 'spathe_dimensions'),
        'spathe_width':                     dim_w(cap, 'spathe_dimensions'),
        'spadix_length':                    meas(cap, 'spadix_length'),
        'perianth_length':                  dim_l(fl, 'perianth_dimensions'),
        'perianth_width':                   dim_w(fl, 'perianth_dimensions'),
        'perianth_outer_length':            dim_l(fl, 'perianth_outer_dimensions'),
        'perianth_outer_width':             dim_w(fl, 'perianth_outer_dimensions'),
        'perianth_inner_length':            dim_l(fl, 'perianth_inner_dimensions'),
        'perianth_inner_width':             dim_w(fl, 'perianth_inner_dimensions'),
        'perianth_tube_length':             meas(fl, 'perianth_tube_length'),
        'perianth_lobes_length':            dim_l(fl, 'perianth_lobes_dimensions'),
        'perianth_lobes_width':             dim_w(fl, 'perianth_lobes_dimensions'),
        'staminate_perianth_tube_length':   meas(fl, 'staminate_perianth_tube_length'),
        'pistillate_perianth_tube_length':  meas(fl, 'pistillate_perianth_tube_length'),
        'pappus_length':                    meas(cap, 'pappus_length'),
        'umbellet_length':                  meas(inf, 'umbellet_length'),
        'labellum_length':                  dim_l(fl, 'labellum_dimensions'),
        'labellum_width':                   dim_w(fl, 'labellum_dimensions'),
        'calyx_length':                     dim_l(fl, 'calyx_dimensions'),
        'calyx_width':                      dim_w(fl, 'calyx_dimensions'),
        'calyx_teeth_length':               dim_l(fl, 'calyx_teeth_dimensions'),
        'calyx_teeth_width':                dim_w(fl, 'calyx_teeth_dimensions'),
        'calyx_lobes_length':               dim_l(fl, 'calyx_lobe_dimensions'),
        'calyx_lobes_width':                dim_w(fl, 'calyx_lobe_dimensions'),
        'upper_calyx_length':               meas(fl, 'upper_calyx_length'),
        'lower_calyx_length':               meas(fl, 'lower_calyx_length'),
        'inner_calyx_lobes_length':         dim_l(fl, 'inner_calyx_lobes_dimensions'),
        'inner_calyx_lobes_width':          dim_w(fl, 'inner_calyx_lobes_dimensions'),
        'outer_calyx_lobes_length':         dim_l(fl, 'outer_calyx_lobes_dimensions'),
        'outer_calyx_lobes_width':          dim_w(fl, 'outer_calyx_lobes_dimensions'),
        'calyx_tube_length':                dim_l(fl, 'calyx_tube_dimensions'),
        'calyx_tube_width':                 dim_w(fl, 'calyx_tube_dimensions'),
        'male_calyx_length':                dim_l(fl, 'male_calyx_dimensions'),
        'male_calyx_width':                 dim_w(fl, 'male_calyx_dimensions'),
        'male_calyx_lobes_length':          dim_l(fl, 'male_calyx_lobe_dimensions'),
        'male_calyx_lobes_width':           dim_w(fl, 'male_calyx_lobe_dimensions'),
        'female_calyx_length':              dim_l(fl, 'female_calyx_dimensions'),
        'female_calyx_width':               dim_w(fl, 'female_calyx_dimensions'),
        'female_calyx_lobes_length':        dim_l(fl, 'female_calyx_lobe_dimensions'),
        'female_calyx_lobes_width':         dim_w(fl, 'female_calyx_lobe_dimensions'),
        'male_calyx_lobes_length_inner':    meas(fl, 'male_calyx_inner_lobe_length'),
        'male_calyx_lobes_length_outer':    dim_l(fl, 'male_calyx_outer_lobe_dimensions'),
        'male_calyx_lobes_width_outer':     dim_w(fl, 'male_calyx_outer_lobe_dimensions'),
        'male_calyx_tube_length':           meas(fl, 'male_calyx_tube_length'),
        'female_calyx_lobes_length_inner':  dim_l(fl, 'female_calyx_inner_lobe_dimensions'),
        'female_calyx_lobes_length_outer':  dim_l(fl, 'female_calyx_outer_lobe_dimensions'),
        'female_calyx_lobes_width_inner':   dim_w(fl, 'female_calyx_inner_lobe_dimensions'),
        'female_calyx_lobes_width_outer':   dim_w(fl, 'female_calyx_outer_lobe_dimensions'),
        'inner_calyx_length':               meas(fl, 'inner_calyx_length'),
        'outer_calyx_length':               meas(fl, 'outer_calyx_length'),
        'corolla_length':                   dim_l(fl, 'corolla_dimensions'),
        'corolla_width':                    dim_w(fl, 'corolla_dimensions'),
        'corolla_tube_length':              dim_l(fl, 'corolla_tube_dimensions'),
        'corolla_tube_width':               dim_w(fl, 'corolla_tube_dimensions'),
        'corolla_lobes_length':             dim_l(fl, 'corolla_lobe_dimensions'),
        'corolla_lobes_width':              dim_w(fl, 'corolla_lobe_dimensions'),
        'upper_corolla_length':             meas(fl, 'upper_corolla_length'),
        'lower_corolla_length':             meas(fl, 'lower_corolla_length'),
        'upper_corolla_lobes_length':       meas(fl, 'upper_corolla_lobes_length'),
        'lower_corolla_lobes_length':       meas(fl, 'lower_corolla_lobes_length'),
        'corolla_lip_length':               meas(fl, 'corolla_lip_length'),
        'staminate_corolla_length':         meas(fl, 'staminate_corolla_length'),
        'pistillate_corolla_length':        meas(fl, 'pistillate_corolla_length'),
        'staminate_corolla_tube_length':    dim_l(fl, 'staminate_corolla_tube_dimensions'),
        'staminate_corolla_tube_width':     dim_w(fl, 'staminate_corolla_tube_dimensions'),
        'pistillate_corolla_tube_length':   dim_l(fl, 'pistillate_corolla_tube_dimensions'),
        'pistillate_corolla_tube_width':    dim_w(fl, 'pistillate_corolla_tube_dimensions'),
        'female_corolla_lobes_length':      dim_l(fl, 'female_corolla_lobe_dimensions'),
        'female_corolla_lobes_width':       dim_w(fl, 'female_corolla_lobe_dimensions'),
        'male_corolla_lobes_length':        dim_l(fl, 'male_corolla_lobe_dimensions'),
        'male_corolla_lobes_width':         dim_w(fl, 'male_corolla_lobe_dimensions'),
        'fruit_length':                     meas(fr, 'fruit_length'),
        'fruit_width':                      meas(fr, 'fruit_width'),
        'fruit_diameter':                   meas(fr, 'fruit_diameter'),
        'seeds_perfruit':                   meas(fr, 'seeds_perfruit'),
        'seed_length':                      meas(fr, 'seed_length'),
        'seed_width':                       meas(fr, 'seed_width'),
        'seed_diameter':                    meas(fr, 'seed_diameter'),
        'pistillate_peduncle_length':       dim_l(inf, 'pistillate_peduncle_dimensions'),
        'pistillate_peduncle_width':        dim_w(inf, 'pistillate_peduncle_dimensions'),
        'staminate_pedicel_length':         dim_l(inf, 'staminate_pedicel_dimensions'),
        'staminate_peduncle_length':        dim_l(inf, 'staminate_peduncle_dimensions'),
        'staminate_peduncle_width':         dim_w(inf, 'staminate_peduncle_dimensions'),
        'species_key': f"{fam.lower()}_{gen.lower()}_{sp.lower()}" if fam and gen and sp else None,
    }

def results_to_df(result):
    row = result_to_row(result)
    gs_cols = manual_extracted_data_df.columns.tolist()
    return pd.DataFrame([row])[gs_cols]
