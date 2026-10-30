precision highp float;

attribute         vec3 a_Position;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform         mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;


void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;
 
  // rotate 
 vec2 newcoord_rot;
 vec2 newcoord_trans = varCoord;
 newcoord_trans -= vec2(0.5,0.5);
 vec2 varCoordRotated;
 varCoordRotated.x =  newcoord_trans.x*cos( oparam4 )-newcoord_trans.y*sin( oparam4 );
 varCoordRotated.y =  newcoord_trans.y*cos( oparam4 )+newcoord_trans.x*sin( oparam4 );
 varCoordRotated += vec2(0.5,0.5);
 varCoordRotated.x /= 3.;
 varCoordRotated.x += 1./3.;

 vec2 varCoordInverted;
 varCoordInverted = vec2( varCoord.x, 1. - varCoord.y );
 varCoordInverted.x /= 3.;
 
 vec2 varCoordInvertedDupl;
 varCoordInvertedDupl = varCoordInverted;
 varCoordInvertedDupl.x += 2./3.;
 
 varCoord = varCoordInverted * oparam1 +
 	varCoordRotated * oparam2 +
 	 varCoordInvertedDupl * oparam3;
}
