precision highp float;

attribute highp vec3 a_Position;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3;

void main()
{
	vec3 the_pos = a_Position;
	the_pos.x += mix(0.,-24., oparam2);
	
	gl_Position = MVPMatrix * vec4(the_pos, 1.0);
	varCoord = a_TextureCoordinate.st;
	varCoord.x *= 0.5;
	varCoord.x += oparam1; 
}
