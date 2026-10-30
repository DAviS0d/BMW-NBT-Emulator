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
varying mediump vec2 varCoord1;
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


//ROTATION FUNCTION
vec3 rotate_y(vec3 point, float angle){
	vec3 ret;
	ret.x = cos(angle)*point.x + sin(angle)* point.z;
	ret.y = point.y;
	ret.z = -sin(angle)*point.x + cos(angle)* point.z;
 	return ret;
}

void main(){
 float _pointer_offset = oparam2;
 float _upscale = clamp(oparam1 * 4.18, (0.0 + _pointer_offset), (4.18 - _pointer_offset));
 vec3 the_pos = a_Position;
 vec3 container_rotate_y = rotate_y(the_pos, _upscale+ _pointer_offset);

 gl_Position = MVPMatrix * vec4(container_rotate_y, 1.0);
 varCoord = a_TextureCoordinate.st;
 varCoord1 = a_TextureCoordinate1.st;
 vec3 eyeDir = normalize(a_Position - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
}
