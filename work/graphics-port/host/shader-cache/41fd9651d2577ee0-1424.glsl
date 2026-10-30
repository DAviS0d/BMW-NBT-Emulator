precision mediump float;
uniform sampler2D tex0,tex1,tex2,tex3;

varying mediump vec2 varCoord, varCoord1;


uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float ambient;
varying mediump float specular;

varying mediump vec3 nrml;

#define RGB(r,g,b) vec3(r/255., g/255., b/255.)

/*

oparam6 = specular

*/


void main()
{
	
 // AMBIENT
 vec3 base_color = RGB(60., 60., 60.); 
 vec3 ambientColor = base_color * ambient;

 // SPECULAR
 vec3 specular_color = RGB(100., 100., 100.);

 gl_FragColor.rgb = ambientColor.rgb;
 gl_FragColor.rgb += (specular * specular_color);
 gl_FragColor.a = oparam0;
}