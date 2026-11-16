"""Structural alignment for the two supported 4-column, 25-row OMR forms.

The answer columns are the anchors. Names, exam titles and filled choices do
not select the layout. Repeated A/B/C/D glyphs are not global feature anchors.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import cv2
import numpy as np


def red_print(image: np.ndarray) -> np.ndarray:
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    return (((hsv[:,:,0]<25)|(hsv[:,:,0]>140)) &
            (hsv[:,:,1]>20) & (hsv[:,:,2]>25)).astype(np.uint8)*255


def order_quad(points: np.ndarray) -> np.ndarray:
    points=np.asarray(points,np.float32).reshape(4,2)
    # A supported upright column has two top and two bottom vertices.
    top=points[np.argsort(points[:,1])[:2]]
    bottom=points[np.argsort(points[:,1])[2:]]
    return np.array([top[np.argmin(top[:,0])],top[np.argmax(top[:,0])],
                     bottom[np.argmax(bottom[:,0])],bottom[np.argmin(bottom[:,0])]],np.float32)


def _iou(a,b):
    ax,ay,aw,ah=cv2.boundingRect(a);bx,by,bw,bh=cv2.boundingRect(b)
    inter=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    return inter/max(1,aw*ah+bw*bh-inter)


def find_columns(image: np.ndarray) -> list[np.ndarray]:
    color=cv2.morphologyEx(red_print(image),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,35,10)
    ink=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((2,2),np.uint8))
    contours=[]
    for mask in (color,ink):
        detected,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(detected)
    candidates=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if h<image.shape[0]*.22 or not .12<w/h<.36:
            continue
        if cv2.contourArea(contour)<w*h*.64:
            continue
        hull=cv2.convexHull(contour)
        quad=cv2.approxPolyDP(hull,cv2.arcLength(hull,True)*.015,True)
        if len(quad)!=4 or not cv2.isContourConvex(quad):
            continue
        quad=order_quad(quad)
        if cv2.contourArea(quad)<w*h*.80:
            continue
        # A frame touching the photo edge may have a clipped top/bottom row.
        if x<2 or y<2 or x+w>image.shape[1]-2 or y+h>image.shape[0]-2:
            continue
        candidates.append(quad)
    unique=[]
    for quad in sorted(candidates,key=cv2.contourArea,reverse=True):
        if not any(_iou(quad,other)>.65 for other in unique):
            unique.append(quad)
    return sorted(unique,key=lambda q:float(q[:,0].mean()))[:24]


def _column_view(image,quad):
    target=np.float32([[0,0],[159,0],[159,899],[0,899]])
    return cv2.warpPerspective(image,cv2.getPerspectiveTransform(quad,target),(160,900))


def identify_layout(image,columns):
    votes=[]
    for quad in columns:
        panel=_column_view(image,quad)
        mask=red_print(panel)>0
        # Long horizontal bands distinguish Retina from the practice form.
        profile=mask[:,35:150].mean(axis=1)
        profile=np.convolve(profile,np.ones(5)/5,mode='same')
        active=profile>.40
        edges=np.diff(np.r_[False,active,False].astype(np.int8))
        bands=[(a,b) for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if b-a>=6]
        body_bands=[(a,b) for a,b in bands if a>18 and b<899]
        if profile[:25].mean()>.65:
            votes.append('practice-book')
        elif profile[:25].mean()<.35 and len(body_bands)>=10:
            votes.append('retina')
        else:
            votes.append(None)
    if len(set(votes))==1 and votes[0] is not None:
        return votes[0]
    return None


def column_groups(image,columns):
    groups=[]
    for group in combinations(columns,4):
        bounds=[cv2.boundingRect(q) for q in group]
        heights=np.array([h for x,y,w,h in bounds],float)
        widths=np.array([w for x,y,w,h in bounds],float)
        tops=np.array([q[:2,1].mean() for q in group])
        bottoms=np.array([q[2:,1].mean() for q in group])
        if heights.max()/heights.min()>1.22 or widths.max()/widths.min()>1.45:
            continue
        if np.ptp(tops)>.16*heights.mean() or np.ptp(bottoms)>.16*heights.mean():
            continue
        centers=np.array([q[:,0].mean() for q in group])
        spacing=np.diff(centers)
        if spacing.min()<.72*widths.mean() or spacing.max()/spacing.min()>1.45:
            continue
        if any(_iou(a,b)>.08 for a,b in zip(group,group[1:])):
            continue
        layout=identify_layout(image,group)
        if layout:
            groups.append((layout,list(group)))
    return groups


@dataclass
class GridEvidence:
    centers: np.ndarray
    supported: np.ndarray
    coverage: float
    row_coverage: list[int]
    method: str = 'column_frames'


def locate_rows(panel,layout):
    """Locate printed row bands, then require the complete monotonic row lattice."""
    if layout=='retina':
        chroma=panel[:,:,2].astype(float)-panel[:,:,1].astype(float)
        profile=np.median(chroma[:,35:150],axis=1)
        profile=np.convolve(profile,np.ones(5)/5,mode='same')
        low,high=np.percentile(profile[35:895],[15,85])
        if high-low<8:return None
        active=profile>(low+high)/2
        count=13;first=49;last=882;minimum=10
    else:
        profile=(red_print(panel)[:,35:150]>0).mean(axis=1)
        profile=np.convolve(profile,np.ones(5)/5,mode='same')
        active=profile>.36
        count=25;first=61;last=879;minimum=7
    active[:35]=False;active[897:]=False
    edges=np.diff(np.r_[False,active,False].astype(np.int8))
    candidates=np.array([(a+b-1)/2 for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if minimum<=b-a<40])
    if len(candidates)<count-3:return None
    expected=np.linspace(first,last,count)
    pitch=(last-first)/(count-1)
    chosen=np.full(count,np.nan)
    used=set()
    for i,y in enumerate(expected):
        near=np.argsort(abs(candidates-y))
        for index in near:
            if index not in used and abs(candidates[index]-y)<pitch*.48:
                chosen[i]=candidates[index];used.add(int(index));break
    present=np.flatnonzero(np.isfinite(chosen))
    if len(present)<count-3 or 0 not in present or count-1 not in present:return None
    chosen=np.interp(np.arange(count),present,chosen[present])
    if np.diff(chosen).min()<pitch*.65 or np.diff(chosen).max()>pitch*1.35:return None
    if layout=='retina':
        return np.interp(np.arange(25),np.arange(0,25,2),chosen)
    return chosen


def _circle_points(image,template):
    x0,y0,x1,y1=template.roi
    gray=cv2.cvtColor(image[y0:y1,x0:x1],cv2.COLOR_BGR2GRAY)
    circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1,12,param1=70,param2=12,minRadius=5,maxRadius=12)
    if circles is None:
        return np.empty((0,2),np.float32)
    return circles[0,:,:2]+np.float32([x0,y0])


def refine_columns(image,template,quads):
    """Correct small border-fit errors using spatially bounded circle matches.

    No correspondence may jump by half a question row or one answer option.
    The maximum correction is also bounded, preventing a one-row/option shift.
    """
    points=_circle_points(image,template)
    if not len(points):return image
    result=image.copy()
    for col,quad in enumerate(quads):
        expected=template.centers[col*25:(col+1)*25].reshape(-1,2)
        distance=np.linalg.norm(expected[:,None,:]-points[None,:,:],axis=2)
        nearest=distance.argmin(axis=1)
        keep=distance[np.arange(100),nearest]<10
        source=points[nearest[keep]];target=expected[keep]
        if len(source)<50 or np.ptp(target[:,1])<np.ptp(expected[:,1])*.75:
            continue
        transform,inliers=cv2.findHomography(source,target,cv2.RANSAC,2.0)
        if transform is None or inliers is None or int(inliers.sum())<40:
            continue
        moved=cv2.perspectiveTransform(expected.reshape(-1,1,2),transform).reshape(-1,2)
        if np.linalg.norm(moved-expected,axis=1).max()>10:
            continue
        patch=cv2.warpPerspective(image,transform,(image.shape[1],image.shape[0]),borderValue=(255,255,255))
        mask=np.zeros(image.shape[:2],np.uint8)
        cv2.fillConvexPoly(mask,quad.astype(np.int32),255)
        result[mask>0]=patch[mask>0]
    return result


def validate_grid(image,template,strict=True,predicted=None) -> GridEvidence | None:
    """Require actual circular cells at the predicted 25x4 lattice in ALL columns."""
    points=_circle_points(image,template)
    if not len(points):return None
    centers=template.centers.copy() if predicted is None else predicted.copy()
    supported=np.zeros((100,4),bool)
    max_distance=min(template.radius*.80,6.5)
    for row,line in enumerate(centers):
        for option,point in enumerate(line):
            distances=np.linalg.norm(points-point,axis=1)
            index=int(distances.argmin())
            if distances[index]<=max_distance:
                supported[row,option]=True
    row_counts=[]
    for col in range(4):
        section=supported[col*25:(col+1)*25]
        rows=int((section.sum(axis=1)>=2).sum())
        row_counts.append(rows)
        if (rows<18 or int(section[:3].sum())<5 or int(section[-3:].sum())<5
                or int(section.sum(axis=0).min())<14):
            if strict:return None
    if strict and supported.mean()<.65:
        return None
    return GridEvidence(centers,supported,float(supported.mean()),row_counts)


def square_markers(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    markers=[]
    for threshold in (110,90,140):
        mask=(gray<threshold).astype(np.uint8)*255
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,w,h=cv2.boundingRect(contour)
            if not (5<=w<=45 and 5<=h<=45 and .7<w/h<1.4):continue
            if w*h<image.shape[0]*image.shape[1]*.000025:continue
            if mask[y:y+h,x:x+w].mean()/255<.80:continue
            quad=cv2.approxPolyDP(contour,cv2.arcLength(contour,True)*.05,True)
            if len(quad)!=4 or not cv2.isContourConvex(quad):continue
            ordered=order_quad(quad)
            if abs(ordered[1,1]-ordered[0,1])>h*.35 or abs(ordered[3,0]-ordered[0,0])>w*.35:continue
            center=np.array([x+(w-1)/2,y+(h-1)/2],np.float32)
            if not any(np.linalg.norm(center-p)<4 for p in markers):markers.append(center)
    return markers[:24]


def marker_quads(image):
    for points in combinations(square_markers(image),4):
        quad=order_quad(np.array(points))
        if not cv2.isContourConvex(quad):continue
        top=np.linalg.norm(quad[1]-quad[0]);bottom=np.linalg.norm(quad[2]-quad[3])
        height=(np.linalg.norm(quad[3]-quad[0])+np.linalg.norm(quad[2]-quad[1]))/2
        if top<image.shape[1]*.25 or not .65<top/bottom<1.5 or not .6<height/top<1.6:continue
        if abs(quad[1,1]-quad[0,1])>top*.20 or abs(quad[2,1]-quad[3,1])>bottom*.20:continue
        if cv2.contourArea(quad)<image.shape[0]*image.shape[1]*.10:continue
        yield quad


def predict_centers(image,template,reference_quads,source_quads):
    predicted=template.centers.copy()
    canonical=np.float32([[0,0],[159,0],[159,899],[0,899]])
    for col,(source,target) in enumerate(zip(source_quads,reference_quads)):
        rows=locate_rows(_column_view(image,source),template.id)
        if rows is None:return None
        to_panel=cv2.getPerspectiveTransform(target,canonical)
        original=template.centers[col*25:(col+1)*25]
        points=cv2.perspectiveTransform(original.reshape(-1,1,2),to_panel).reshape(25,4,2)
        points[:,:,0]=np.median(points[:,:,0],axis=0)[None,:]
        points[:,:,1]=rows[:,None]
        predicted[col*25:(col+1)*25]=cv2.perspectiveTransform(points.reshape(-1,1,2),np.linalg.inv(to_panel)).reshape(25,4,2)
    return predicted


class StructuralAligner:
    def __init__(self,templates,specifications):
        self.templates={t.id:t for t in templates}
        self.specifications=specifications
        template=self.templates['retina']
        options=[]
        for quad in marker_quads(template.image):
            if all(cv2.pointPolygonTest(quad,tuple(map(float,p)),False)>0 for p in template.centers.reshape(-1,2)):
                options.append(quad)
        calibrated=specifications['retina'].get('markers')
        self.reference_markers=np.asarray(calibrated,np.float32) if calibrated else min(options,key=cv2.contourArea) if options else None

    def align(self,image):
        results=[]
        columns=find_columns(image)
        for layout,group in column_groups(image,columns):
            template=self.templates[layout]
            quads=np.array(self.specifications[layout]['columns'],np.float32)
            predicted=predict_centers(image,template,quads,group)
            if predicted is None:continue
            src_pts=np.concatenate(group,axis=0)
            dst_pts=np.concatenate(quads,axis=0)
            H,_=cv2.findHomography(src_pts,dst_pts)
            if H is None:continue
            aligned=cv2.warpPerspective(image,H,(template.image.shape[1],template.image.shape[0]),borderValue=(255,255,255))
            for source,target in zip(group,quads):
                transform=cv2.getPerspectiveTransform(source,target)
                patch=cv2.warpPerspective(image,transform,(aligned.shape[1],aligned.shape[0]),borderValue=(255,255,255))
                mask=np.zeros(aligned.shape[:2],np.uint8)
                cv2.fillConvexPoly(mask,target.astype(np.int32),255)
                aligned[mask>0]=patch[mask>0]
            evidence=validate_grid(aligned,template,predicted=predicted)
            if evidence is not None:
                results.append((evidence.coverage,template,aligned,evidence))
        if results:return max(results,key=lambda r:r[0])
        # Retina's four black squares remain usable when JPEG/color processing
        # breaks thin red borders into disconnected segments.
        if self.reference_markers is not None:
            template=self.templates['retina']
            quads=np.array(self.specifications['retina']['columns'],np.float32)
            for source in marker_quads(image):
                transform=cv2.getPerspectiveTransform(source,self.reference_markers)
                aligned=cv2.warpPerspective(image,transform,(template.image.shape[1],template.image.shape[0]),borderValue=(255,255,255))
                if identify_layout(aligned,quads)!='retina':continue
                predicted=predict_centers(aligned,template,quads,quads)
                if predicted is None:continue
                evidence=validate_grid(aligned,template,predicted=predicted)
                if evidence is not None:
                    evidence.method='registration_marks'
                    return evidence.coverage,template,aligned,evidence
        return None
