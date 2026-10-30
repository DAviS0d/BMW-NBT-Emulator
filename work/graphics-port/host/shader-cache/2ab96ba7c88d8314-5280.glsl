precision highp float;

attribute vec3 a_Position;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform         mat4 MVPMatrix;
uniform  mat4 ModelViewInverse;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
varying mediump vec3 LightPosModel;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoordOrange;
varying mediump vec2 varCoordOrangePress;
varying mediump vec2 varCoordColor;
varying mediump vec4 preMultiplyOparam;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;

varying lowp vec3  LightVec;

void main(){
  gl_Position = MVPMatrix * vec4(a_Position, 1.0);
  vec2 varCoord = a_TextureCoordinate.st;
  mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
  ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
  ReflectDir.xy = ReflectDir.xy * 0.5 + 0.5;
  varCoordColor = vec2( clamp(1.0 - varCoord.y, 0., 1.), varCoord.x );
  
  varCoordOrange = vec2( 1.0 - varCoord.x, varCoord.y );
  varCoordOrangePress = vec2( 1.0 - varCoord.y, varCoord.x );
  
  preMultiplyOparam = vec4(0.6, oparam2, oparam3, oparam1 ) * oparam0;
}
