precision highp float;

attribute float a_Color;
attribute vec2 a_TextureCoordinate;
attribute vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform mat4 MVPMatrix;
uniform mat3 ModelWorld;
uniform vec3 LightPosModel;
varying mediump vec2 varCoord;
varying mediump float vc;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;



void main()
{
	vc = a_Color;
	vc = step(0.2,vc);
	
	vec3 t_pos = a_Position;
	t_pos.x += vc * oparam1;
	gl_Position = MVPMatrix * vec4(t_pos, 1.0);
	
	varCoord = a_TextureCoordinate.st;
	varCoord.y *= 0.25;
	varCoord.y += oparam5 * 0.25; 
}
