precision highp float;

attribute         vec3 a_Position;
attribute mediump float a_Color;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform         mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec3 ReflectDir;
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
uniform mediump float oparam5;
varying mediump float edge_alpha;


void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;
 edge_alpha = a_Color;
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
}
