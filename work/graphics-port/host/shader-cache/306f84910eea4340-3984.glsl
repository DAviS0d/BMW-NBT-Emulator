precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
varying mediump vec2 varCoord,cutout_coords,content_coords;
varying mediump vec4 varFade;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	#define _mirror(A, B) (1.-step(A,B))
 
	varCoord = a_TextureCoordinate.st;
	vec2 mirrored_coords = varCoord;
	mirrored_coords.y =  2.0 * abs(_mirror( mirrored_coords.y, 0.5 ) - mirrored_coords.y);
	varCoord = mirrored_coords;
 
	cutout_coords = a_TextureCoordinate1.st;

	content_coords = vec2( a_Normal.x, 1.-a_Normal.y);
	content_coords.x *= oparam7;

	varFade = vec4( vec3( oparam6 * oparam0 ), oparam0 );
}
