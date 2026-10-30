precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


/*** ROTATION FUNCTION **************/
vec3 rotate_y(vec3 point, float angle)
{
	vec3 ret;
	ret.x = cos(angle)*point.x + sin(angle)* point.z;
	ret.y = point.y;
	ret.z = -sin(angle)*point.x + cos(angle)* point.z;
 	return ret;
}

void main()
{
	float _pointer_offset = oparam2;
	float _upscale = clamp(oparam1 * 4.18, (0.0 + _pointer_offset), (4.18 - _pointer_offset));
	vec3 the_pos = a_Position;
	vec3 container_rotate_y = rotate_y(the_pos, _upscale + _pointer_offset);

	gl_Position = MVPMatrix * vec4(container_rotate_y, 1.0);
	varCoord = a_TextureCoordinate.st;
}
