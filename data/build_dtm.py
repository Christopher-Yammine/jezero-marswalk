# Resamples the USGS Mars 2020 TRN CTX DTM (20 m GeoTIFF) to the planner 30 m grid.
# usage: python -I build_dtm.py <dtm.tif> ../m20_traverse.json jez_dtm_30m.i16 jez_dtm_30m.json
# needs: pip install tifffile imagecodecs numpy
import sys, json, math, tifffile, numpy as np
dtm_path, trav_path, out_bin, out_json = sys.argv[1:5]
R=3396190.0; MPD=R*math.pi/180; CELL=30
JEZ=[[18.3067994,77.2229331],[18.669315,77.583964]]
lat0,lat1,lon0,lon1=JEZ[1][0],JEZ[0][0],JEZ[0][1],JEZ[1][1]
latC=(lat0+lat1)/2; mLon=MPD*math.cos(math.radians(latC)); mLat=MPD
nx=math.ceil((lon1-lon0)*mLon/CELL); ny=math.ceil((lat0-lat1)*mLat/CELL)
print('grid',nx,ny)
with tifffile.TiffFile(dtm_path) as t:
    pg=t.pages[0]; a=pg.asarray().astype(np.float64)
    sx,sy,_=pg.tags['ModelPixelScaleTag'].value
    tp=pg.tags['ModelTiepointTag'].value; tx,ty=tp[3],tp[4]
H,W=a.shape
nod=a<-1e30; a[nod]=np.nan
def sample(lat,lon):
    # equirectangular sphere, lat_ts=0: x=R*lon_rad, y=R*lat_rad; pixel-is-area, centre at +0.5
    c=(MPD*lon-tx)/sx-0.5; r=(ty-MPD*lat)/sy-0.5
    c0=np.floor(c).astype(int); r0=np.floor(r).astype(int); fc=c-c0; fr=r-r0
    ok=(c0>=0)&(r0>=0)&(c0<W-1)&(r0<H-1)
    c0=np.clip(c0,0,W-2); r0=np.clip(r0,0,H-2)
    v=(a[r0,c0]*(1-fc)*(1-fr)+a[r0,c0+1]*fc*(1-fr)+a[r0+1,c0]*(1-fc)*fr+a[r0+1,c0+1]*fc*fr)
    v[~ok]=np.nan; return v
ys,xs=np.mgrid[0:ny,0:nx]
lat=lat0-(ys+.5)*CELL/mLat; lon=lon0+(xs+.5)*CELL/mLon
e=sample(lat.ravel(),lon.ravel())
print('cells',e.size,'nan',int(np.isnan(e).sum()),'min',np.nanmin(e),'max',np.nanmax(e))
dm=np.where(np.isnan(e),-32768,np.round(e*10)).astype('<i2')
dm.tofile(out_bin)
# agreement with rover track elevations
d=json.load(open(trav_path))
P=[(p[1],p[0],p[2]) for s in d['segments'] for p in s['pts'] if p[2] is not None]
P=np.array(P); dv=sample(P[:,0],P[:,1]); diff=dv-P[:,2]; diff=diff[~np.isnan(diff)]
stats=dict(n=int(diff.size),mean=float(diff.mean()),median=float(np.median(diff)),std=float(diff.std()),p95abs=float(np.percentile(np.abs(diff),95)))
print('DTM minus rover:',stats)
json.dump(dict(nx=nx,ny=ny,cell=CELL,units='decimetres',nodata=-32768,source='USGS Mars 2020 TRN CTX DTM 20 m, JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m',resampled='bilinear at 30 m cell centres',dtm_minus_rover_m=stats),open(out_json,'w'),indent=1)
