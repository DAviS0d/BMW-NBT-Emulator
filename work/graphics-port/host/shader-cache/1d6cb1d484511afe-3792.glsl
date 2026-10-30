precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
varying mediump vec2 varCoord;
varying mediump vec4 varFade;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float alphaFalloff;


void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	#define _mirror(A, B) (1.-step(A,B))
 
	varCoord = a_TextureCoordinate.st;
	vec2 mirrored_coords = varCoord;
	mirrored_coords.y =  2.0 * abs(_mirror(mirrored_coords.y, 0.5) - mirrored_coords.y);
	varCoord = mirrored_coords;
 	
	varFade = vec4(vec3(oparam6 * oparam0), oparam0);
}
